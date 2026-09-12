# 11 — India / Gujarat / Current P2P Context

## Project Position

GridShare is a hackathon prototype and software architecture. It must not claim that a generic residential P2P retail-energy market is universally open for unrestricted consumer trading in India.

Production deployment would require the relevant utility, regulator and authorized-market integration.

## Current Useful Signals from Indian P2P Pilot Material

### BSES Rajdhani Power Limited (BRPL)
BRPL currently describes P2P trading as a government-supported pilot with DISCOMs, India Energy Stack and authorized Trading Platform Providers. The page describes:
- consumer/prosumer participation
- smart-meter / net-meter prerequisites
- DISCOM verification
- digital verified credentials (VC)
- authorized trading apps
- bill-based settlement

This strengthens our architecture's inclusion of **identity/utility verification before trading** and **utility-linked settlement**, while still keeping the hackathon's settlement simulated.

Source:
https://www.bsesdelhi.com/web/brpl/p-to-p-trading

### PVVNL
PVVNL's current P2P page describes a seven-step journey including:
1. verified credential
2. approved app
3. registration
4. trade request/list surplus
5. day-ahead trading for tomorrow
6. DISCOM meter verification
7. settlement adjusted in the electricity bill

This is the strongest reason to make **day-ahead** the initial market mode in our domain, while using current/updated telemetry for forecasting and grid validation rather than claiming same-day regulated retail trading.

Source:
https://www.pvvnl.org/P2P-Energy-Trading

### CEA AMI
CEA's AMI functional requirements include two-way communication, remote meter reading, TOD/TOU metering, net metering/billing and event detection, with AMI data serving as a repository for validated/edited meter data and downstream analytics.

Source:
https://cea.nic.in/wp-content/uploads/2020/04/ami_func_req.pdf

## Gujarat Relevance

The team's research document identifies Gujarat as a useful demonstration context because GERC has active rooftop/distributed-renewable regulation and 2026 work relating to virtual net metering/distributed renewable energy frameworks.

Do not present emerging/draft provisions as completed law.

## Pulse Energy / EV Optimization Insight

Pulse Energy's 2025 article on AI-powered EV charging describes a pattern directly relevant to our architecture:
- ingest grid-demand forecasts
- learn usage behavior
- use dynamic rates
- optimize charging windows
- reduce grid strain
- coordinate renewable availability

We treat this as a design reference for flexible-load optimization, not as a regulatory source.

Source:
https://pulseenergy.io/blog/ai-powered-ev-charging-software

## Architecture Changes Caused by This Research

Compared with a generic P2P marketplace, GridShare explicitly includes:

```text
User
  -> Utility identity / verified credential
  -> Asset/meter verification
  -> Market eligibility
  -> Day-ahead order
  -> Grid-aware clearing
  -> Meter-based reconciliation
  -> Utility-style bill/settlement representation
```

The physical supply remains uninterrupted and is managed by the distribution network.
