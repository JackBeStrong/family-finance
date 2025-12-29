# Active Context

This file tracks the project's current status, including recent changes, current goals, and open questions.

## Current Focus

* **Phase 1 Development**: Bank statement reader module - CORE COMPLETE
* Transaction categorization system (next step)
* Summary report generation

## Recent Changes

* [2025-12-29 14:03:28 AEDT] - Project initialized
* [2025-12-29 14:03:28 AEDT] - Memory Bank created
* [2025-12-29 14:03:28 AEDT] - Initial project scope defined
* [2025-12-29 14:44:00 AEDT] - Implemented parser architecture with plugin pattern
* [2025-12-29 14:44:00 AEDT] - Created Westpac CSV parser (148 transactions parsed)
* [2025-12-29 14:44:00 AEDT] - Created ANZ CSV parser (4 transactions parsed)
* [2025-12-29 14:44:00 AEDT] - Normalized output to JSON and CSV formats

## Open Questions/Issues

* ~~Which Australian banks should be prioritized for statement format support?~~ → Started with Westpac and ANZ
* Preferred report output format (PDF, HTML, CSV, or all)?
* Should the system support multiple family members with separate accounts?
* Data privacy considerations - local storage only or cloud backup option?
* Transaction categorization rules - manual, rule-based, or ML-based?
