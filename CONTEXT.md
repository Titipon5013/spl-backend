# ParkPilot — Domain Glossary

## People

| Term | Definition |
|------|------------|
| **Admin** | A parking administrator who uses the ParkPilot dashboard. Authenticates via email/password or Google OAuth and must be manually approved before accessing protected features. |
| **User** | A vehicle owner who registers a license plate for CAMT parking access. Not a dashboard operator. |

## Access Workflows

| Term | Definition |
|------|------------|
| **License Plate Request** | A public registration submitted by a **User** to add a vehicle plate. An **Admin** approves or rejects it; approval copies the plate into the active registry. |
| **Admin Access Request** | A Google OAuth sign-up by a prospective **Admin**. The account stays **pending** until an existing approved **Admin** grants dashboard access. Distinct from license plate registration. |

## Approval States

| Term | Definition |
|------|------------|
| **Pending** | Submitted but not yet reviewed. |
| **Approved** | Reviewed and granted access. |
| **Rejected** | Reviewed and denied. |
| **Revoked** | Previously approved access withdrawn; active sessions are invalidated on next request. |

## Analytics

| Term | Definition |
|------|------------|
| **Event Log** | Append-only record of per-slot occupancy state changes from cameras or MQTT ingestion. |
| **Dwell Time** | Duration a vehicle occupies a slot, measured from an occupied event to the next free event for that slot. |
| **System Health** | Operational status of the Orange Pi board and parking cameras. |
| **Camera Stream** | A live video source connected to the legacy CAMT parking system. Progress I treats Parking Area 1, Parking Area 2, License Check 1, and License Check 2 as the four connected camera streams. |
