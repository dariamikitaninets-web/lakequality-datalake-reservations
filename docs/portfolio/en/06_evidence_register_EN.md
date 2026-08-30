# Evidence register

Only evidence from an actual execution may receive `CAPTURED` status.

| ID | Stage | Expected evidence | Initial status |
|---|---|---|---|
| EV-001 | Preflight | Python, Git, Docker, Java, and JMeter versions on macOS | TO CAPTURE |
| EV-002 | Source data | Preview of the three synthetic sources | TO CAPTURE |
| EV-003 | Architecture | Source-Bronze-Silver-Quarantine-Gold diagram | TO PRODUCE |
| EV-004 | First batch | Fixed-pipeline summary and batch ID | TO CAPTURE |
| EV-005 | Completeness | SQL reconciliation with delta = 0 | TO CAPTURE |
| EV-006 | Uniqueness | SQL check for duplicate booking IDs in Silver | TO CAPTURE |
| EV-007 | Quarantine | Reason codes and record count by cause | TO CAPTURE |
| EV-008 | Latest wins | Controlled failure in buggy mode | TO CAPTURE |
| EV-009 | Defect | BUG-001 in GitHub Issues | TO CAPTURE |
| EV-010 | Correction | Diff or Pull Request showing the correction | TO CAPTURE |
| EV-011 | Regression | Complete successful pytest report | TO CAPTURE |
| EV-012 | Red CI | GitHub Actions blocked in buggy mode | TO CAPTURE |
| EV-013 | Green CI | Successful GitHub Actions run in fixed mode | TO CAPTURE |
| EV-014 | Performance | 10k/100k/500k measurements and throughput | TO CAPTURE |
| EV-015 | Quality report | Indicators and GO/NO-GO recommendation | TO CAPTURE |
| EV-016 | GitLab | Real GitLab pipeline, if an account is created | OPTIONAL |
| EV-017 | Kubernetes | `kubectl get jobs,pods` and Job logs | OPTIONAL |

## Capture convention

- Filename: `EV-XXX_short_description.png`.
- Show the command or query and its primary result.
- Hide tokens, private email addresses, and unnecessary personal paths.
- Add date, environment, commit SHA, and one-sentence interpretation.
- Never recreate an interface or a result that was not executed.
