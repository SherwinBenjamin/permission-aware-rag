# On-call Runbook

This runbook is for engineers on the production on-call rotation.

## Rotation

The rotation is weekly, handing over every Monday at 11:00 JST. Each week has a primary and a secondary on-call engineer. The primary acknowledges pages; the secondary takes over if the primary does not acknowledge within 10 minutes. On-call engineers receive an allowance of 15,000 yen per week on rotation.

## Severity levels

- SEV1: customer-facing outage or data loss. Page immediately, open an incident channel, and notify the engineering manager within 15 minutes.
- SEV2: major feature degraded for many customers. Acknowledge within 15 minutes and post status updates every 30 minutes.
- SEV3: minor degradation with a workaround. Handle during business hours.

## Paging and escalation

Alerts page through PagerDuty. If you cannot resolve a SEV1 within 30 minutes, escalate to the secondary and the service owner. For security incidents, also page the security on-call rotation.

## Database failover

If the primary PostgreSQL instance is unhealthy, check replication lag on the replica dashboard first. If lag is below 5 seconds, promote the replica with the failover script `ops/db-failover.sh --promote`, then update the connection secret in Parameter Store and restart the API pods. Never promote a replica with lag above 60 seconds without approval from the database owner.

## Rolling back a deploy

Every deploy is tagged. To roll back, run the deploy pipeline with the previous tag. Rollbacks do not need approval during an incident, but post the rollback in the incident channel.

## After an incident

Write a blameless postmortem within five working days for every SEV1 and SEV2. Include the timeline, root cause, impact, and action items with owners.
