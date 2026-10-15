# Databricks Free Edition: limits and design consequences

Last verified: 2026-10-06 against
https://docs.databricks.com/aws/en/getting-started/free-edition-limitations

| Limit | Design consequence |
|---|---|
| Serverless compute only; no custom clusters or GPUs | No init scripts or cluster libraries; dependencies go in notebook/job environments |
| Outbound internet restricted to trusted domains; LinkedIn verification unlocks outbound access | External brokers or APIs need verification first; test with a TCP check before designing around them |
| One SQL warehouse, 2X-Small | Keep dashboard and SQL workloads light |
| Max 5 concurrent job tasks per account | Chain tasks rather than fan out wide |
| One active pipeline per pipeline type | Put related tables in one Lakeflow pipeline, or use jobs for the rest |
| Model Serving: limited endpoints, no GPU, no provisioned throughput | Prefer batch scoring; document real-time serving as a production alternative |
| Online tables not supported | No low-latency feature serving; use batch features |
| Daily fair-usage quota; compute stops for the day when exceeded | Small samples, `availableNow` triggers, scheduled micro-batches |
| Inactive accounts may be deleted | Everything must be reproducible from the repository and source data |
| Non-commercial use only | Portfolio and learning projects only |

## Streaming on serverless

Assume `Trigger.AvailableNow` (process what is available, then stop) scheduled by a job.
Continuous or fixed-interval triggers may not be supported on serverless; verify with a spike
before designing a long-running stream.
