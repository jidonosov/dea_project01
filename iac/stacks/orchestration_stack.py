"""Orchestration stack: Step Functions crawl->ETL pipeline on an EventBridge schedule.

DEA-C01:
  D1 - orchestration of a multi-step batch pipeline (crawl catalog, then transform).
  D3 - automation, retries with backoff, X-Ray tracing, and a schedule that's OFF by
       default so it can't quietly run up cost.

Why the crawler step is a poll-loop, not a one-liner (educational note):
  Glue *jobs* have a native Step Functions .sync (RUN_JOB) integration -- Step Functions
  starts the job and blocks until it finishes. Glue *crawlers* do NOT: there's no .sync
  integration for a crawler. So the exam-correct pattern is: start the crawler via the AWS
  SDK service integration (glue:StartCrawler), then poll glue:GetCrawler in a Wait -> Choice
  loop until State == "READY" before moving on. This is a common real-world Step Functions
  shape and a likely DEA-C01 scenario.

Why Step Functions over MWAA/Airflow here: MWAA bills for the environment 24/7 whether it's
orchestrating or idle; Step Functions is pay-per-transition -- the right call on a small budget.
"""
from aws_cdk import (
    Stack,
    Duration,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct


class OrchestrationStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        etl_job_name: str,
        crawler_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        crawler_arn = f"arn:aws:glue:{self.region}:{self.account}:crawler/{crawler_name}"

        # 1. Start the crawler (SDK integration -- no .sync exists for crawlers).
        start_crawler = tasks.CallAwsService(
            self,
            "StartCrawler",
            service="glue",
            action="startCrawler",
            parameters={"Name": crawler_name},
            iam_resources=[crawler_arn],
            result_path=sfn.JsonPath.DISCARD,  # keep the state input; ignore the empty response
        )

        # 3. Poll the crawler's state.
        get_crawler = tasks.CallAwsService(
            self,
            "GetCrawler",
            service="glue",
            action="getCrawler",
            parameters={"Name": crawler_name},
            iam_resources=[crawler_arn],
            result_path="$.crawler",  # -> $.crawler.Crawler.State
        )

        # 2. Give the crawler time before the first poll (and between polls).
        wait = sfn.Wait(
            self, "WaitForCrawler", time=sfn.WaitTime.duration(Duration.seconds(30))
        )

        # 4. Run the ETL (Glue jobs DO have .sync: block until the run completes).
        run_etl = tasks.GlueStartJobRun(
            self,
            "RunCuratedEtl",
            glue_job_name=etl_job_name,
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,  # sync: wait for completion
            result_path="$.etl",
        ).add_retry(max_attempts=2, interval=Duration.seconds(30), backoff_rate=2.0)

        # If the crawler is already running (e.g. a prior execution), skip StartCrawler's error
        # and go straight to polling. SDK integration errors surface as "<Service>.<ErrorName>".
        start_crawler.add_catch(
            wait, errors=["Glue.CrawlerRunningException"], result_path=sfn.JsonPath.DISCARD
        )

        # Choice: once READY, transform; otherwise loop back and wait again.
        crawler_ready = sfn.Choice(self, "CrawlerReady?")
        crawler_ready.when(
            sfn.Condition.string_equals("$.crawler.Crawler.State", "READY"),
            run_etl.next(sfn.Succeed(self, "Done")),
        ).otherwise(wait)

        # Wire the loop: start -> wait -> get -> ready? -> (etl | wait).
        definition = start_crawler.next(wait)
        wait.next(get_crawler)
        get_crawler.next(crawler_ready)

        state_machine = sfn.StateMachine(
            self,
            "Pipeline",
            state_machine_name="dea-c01-pipeline",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.hours(1),  # bounds the poll loop so it can't spin forever
            tracing_enabled=True,
        )

        # Daily trigger (disabled by default so it can't quietly run up cost).
        events.Rule(
            self,
            "DailySchedule",
            schedule=events.Schedule.rate(Duration.days(1)),
            enabled=False,
            targets=[targets.SfnStateMachine(state_machine)],
        )
