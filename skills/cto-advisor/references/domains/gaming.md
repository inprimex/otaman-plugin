# Gaming — Strategic Advisory Reference

## What's distinctive about advising in this domain

Gaming CTO conversations differ from SaaS in that the discipline includes specialized roles SaaS doesn't have (engine programmers, technical artists, tools engineers, DevOps specialized for game pipelines), and the production model is closer to film production than continuous software delivery. Push back on framings that treat games like apps — the team composition, content production budgets, playtesting iteration, platform certification, and live ops are different categories of work that engineering-only thinking misses.

## Vendor landscape

### Game engines

- **Unity**: Default for mobile and 2D/3D mid-scale; broadest talent pool; recent pricing controversies have eroded trust
- **Unreal Engine 5**: Default for AAA-style 3D, especially photoreal; Epic's pricing model favorable for most projects
- **Godot**: Open-source; growing rapidly; viable for 2D and modest 3D; smaller talent pool
- **Custom engine**: Almost never the right call for new studios; existing studios sometimes maintain legacy engines

### Backend services (game-specific)

- **PlayFab** (Microsoft): Mature; broad capability; Microsoft ecosystem ties
- **Beamable**: Modern; Unity-focused; live ops strength
- **Nakama** (Heroic Labs): Open-source + managed; good for multiplayer
- **Unity Gaming Services**: Native to Unity; rapidly maturing
- **AccelByte**: Enterprise-focused; broader feature set
- **Custom on AWS/GCP/Azure**: For specific needs or scale

### Multiplayer / netcode

- **Photon**: Most-used third-party; multiple products (PUN, Quantum, Fusion, Voice)
- **Mirror, FishNet**: Open-source for Unity
- **Unity Netcode for GameObjects**: Native Unity; production-ready
- **Custom dedicated servers**: For competitive games requiring specific architectures

### Anti-cheat

- **Easy Anti-Cheat (Epic)**: Industry standard for PC; included with Epic services
- **BattlEye**: Strong PC; competitor to EAC
- **Vanguard (Riot)**: Kernel-level; controversial trade-offs
- **Unity Anti-Cheat Toolkit**: Lightweight; less robust

### Live ops & analytics

- **GameAnalytics**: Free tier robust; widely used
- **deltaDNA / Unity Analytics**: Player segmentation
- **Custom warehouses (Snowflake, BigQuery + dbt)**: For mature studios with analyst capability

### Monetization SDKs

- **Unity IAP, RevenueCat**: Unified IAP across platforms
- **AppLovin MAX, Google AdMob, Unity Ads**: Mediation for ads
- **ironSource**: Common in mobile gaming

## Hiring patterns

Game studios have specialized roles SaaS teams don't have:

- **First hire profile**: Senior gameplay programmer with relevant engine experience. Engine choice gates hiring pool.
- **Specialized roles unique to gaming**:
  - **Engine programmer** — works on engine internals, performance, tooling
  - **Technical artist** — bridge between art and engineering; shaders, rigs, optimization
  - **Tools programmer** — internal pipeline tools for content creators
  - **Level / encounter designer** — designs game spaces and pacing
  - **Game designer** — systems, balance, economy, progression
  - **Producer** — production management; closer to film producer than scrum master
  - **Sound designer / composer** — often contractor at smaller studios
  - **Narrative designer / writer** — for story-driven games
  - **Community manager** — ongoing player engagement, especially live-ops games
  - **QA specialists** — exploratory testing, compliance testing, certification testing
- **Outsourcing patterns**: Art outsourced extensively (concept, modeling, animation); audio frequently outsourced; localization always outsourced; QA often outsourced (with in-house team for trust); engine and gameplay code rarely outsourced.
- **Contract vs. employee mix**: Higher contractor ratio than SaaS — content production scales up and down with project phase.

## Common architectural debates

### "Unity vs. Unreal vs. Godot"

For mobile / 2D / mid-scale 3D: Unity unless team has Unreal experience and reasons.
For high-fidelity 3D: Unreal is the modern default.
For 2D / indie / small teams with engineering capability: Godot increasingly viable.

The decision is mostly about hiring pool, art pipeline preferences, and existing team experience. Don't switch engines mid-project.

### "Build backend vs. use BaaS"

Default position for new studios: use BaaS (PlayFab, Beamable, Nakama). The categories of work (auth, leaderboards, cloud saves, live ops, matchmaking) are well-served and not differentiating.

Flip when: very specific scale or feature requirements; team has backend specialists; building a backend that's part of competitive differentiation (rare).

### "Single-platform launch vs. multi-platform"

Default position for indies: launch one platform first (usually PC/Steam), expand later. Multi-platform parallel launch multiplies cert work, QA, and platform-specific engineering.

For mobile-only studios: launch both iOS and Android together; the markets are too different to skip.

### "F2P with monetization vs. premium"

Premium for indies with strong narrative or unique mechanics; market is hard but lower live-ops burden.
F2P for studios with retention-driven design and live-ops capacity; higher LTV ceilings but requires sustained content production.
Hybrid (premium with cosmetic IAP, season passes) increasingly common in mid-market.

### "Build live ops platform vs. use BaaS live ops"

Default position: use BaaS live ops capability (PlayFab LiveOps, Beamable). Custom live ops is a multi-year investment.

Flip when: scale or specific event mechanics not supported; team has dedicated live ops engineering capacity.

## Regulatory bottlenecks

- **Console certification (TRC/TCR)**: 2–8 weeks per platform per submission; failures require resubmission
- **App Store review**: typically days, occasionally weeks for novel mechanics; rejections can require redesign
- **ESRB / PEGI / CERO ratings**: 4–8 weeks; resubmission if content changes
- **Loot box regulation**: emerging; varies by jurisdiction; can require monetization redesign
- **China publication license (ISBN)**: 6–18 months; only viable through Chinese publisher partnership
- **GDPR-K / COPPA compliance**: 4–8 weeks for full implementation
- **Anti-cheat platform certification (e.g., for esports tournaments)**: varies by platform

## Common pitfalls in advisory for gaming

- Treating games like apps — content production cost, playtesting iteration, certification overhead
- Engineering-only estimates that ignore content production cost
- Underestimating playtesting and iteration — fun isn't engineered, it's iterated
- Live ops resourcing planned post-launch — the team building the game is rarely the team running it
- Localization treated as translation
- Multiplayer added late — netcode shapes architecture
- Anti-cheat as afterthought
- Underestimating community management investment for live-ops games
- "It's just like [popular game]" — that game cost $100M and took 5 years
- Recommending custom engines (almost always wrong)

## Escalation triggers specific to gaming

- Engine choice is a multi-year commitment — escalate to studio leadership
- Platform exclusivity deals (Epic, Sony, Xbox) involve business and legal alongside engineering
- Major monetization model changes affect game design, business model, and player community
- Content removal or modifications for regulatory reasons (CCP censorship, EU loot box bans) involve legal + business
- Major performance issues at launch require crisis response across community + engineering + production
- Studio-defining narrative decisions (story endings, character treatment) escalate to creative leadership
- IP licensing decisions involve legal + business strategy
