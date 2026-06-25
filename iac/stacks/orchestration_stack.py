"""Orchestration stack: Step Functions crawl->ETL pipeline on an EventBridge schedule.

DEA-C01: D1 (orchestration) and D3 (automation, retries, monitoring).
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

        run_etl = tasks.GlueStartJobRun(
            self,
            "RunCuratedEtl",
            glue_job_name=etl_job_name,
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,  # sync: wait for completion
            result_path="$.etl",
        ).add_retry(max_attempts=2, interval=Duration.seconds(30), backoff_rate=2.0)

        definition = sfn.Pass(
            self,
            "Start",
            comment=f"TODO: StartCrawler({crawler_name}) -> wait ready -> ETL",
        ).next(run_etl).next(sfn.Succeed(self, "Done"))

        state_machine = sfn.StateMachine(
            self,
            "Pipeline",
            state_machine_name="dea-c01-pipeline",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.hours(1),
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
