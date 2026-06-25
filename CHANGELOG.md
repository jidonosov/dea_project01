# Changelog

All notable changes to this project follow [Keep a Changelog](https://keepachangelog.com/)
and [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Initial repository scaffold: CDK (Python) lakehouse skeleton, AI-governance frame
  (`AGENTS.md`), CI/CD with OIDC, Claude Code config, and stub stacks for storage,
  catalog/Glue, orchestration, and governance.
- Storage stack: central S3 server-access-log bucket (audit) and an Athena query-results
  bucket; wired access logging onto the raw and curated zones.
