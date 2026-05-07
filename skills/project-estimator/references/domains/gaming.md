# Gaming — Estimation Reference

## What's distinctive about this domain

Game development estimation differs from SaaS in fundamental ways: production timelines run 12 months to 5+ years for substantial titles; team composition includes specialists (engine programmers, technical artists, level designers, sound designers) absent from typical software teams; platform certification adds 1–4 months of calendar time at the back end; and a meaningful portion of cost goes to content production (art, audio, narrative) rather than code. The most common pre-sales failure is treating a game like an app — scoping features and engineering effort while underbudgeting content production, playtesting iteration, and live ops.

## Compliance frameworks that may apply

| Framework | When it applies | Effort impact |
|---|---|---|
| ESRB / PEGI / CERO / USK rating | Public release on most platforms | minimal direct cost; content decisions affect rating |
| COPPA | US users under 13 | +15–25%; restricted data collection, parental consent |
| GDPR-K (children in EU) | EU users under 16 (varies by country) | +15–25%; similar to COPPA |
| Loot box regulations | Belgium, Netherlands, multiple US states proposing | varies; redesign of monetization may be required |
| Apple App Store / Google Play policies | Mobile distribution | moderate; periodic policy changes can require rework |
| Console TRC / TCR | PlayStation, Xbox, Nintendo certification | +5–15%; specific per-platform technical requirements |
| Online safety (UK Online Safety Act, EU DSA) | User-generated content, communications | +10–25%; content moderation, reporting flows |
| Accessibility (CVAA, EU Accessibility Act) | US/EU markets | +5–15%; subtitles, controls remapping, color blind support |
| Gambling regulations | Real-money gaming, social casino | +30–60%; full gambling license process by jurisdiction |
| Anti-cheat / fair play | Competitive online games | +10–20%; integration with anti-cheat services |

## Common integrations and effort patterns

| Integration class | Typical providers | Effort range | Notes |
|---|---|---|---|
| Game engine | Unity, Unreal, Godot, custom | foundational choice | Engine choice affects everything; rewriting mid-project is catastrophic |
| Backend services | PlayFab, Beamable, Nakama, GameSparks (deprecated), AWS GameLift, Photon | 80–300h | "BaaS for games"; covers auth, leaderboards, cloud saves, multiplayer |
| Multiplayer / netcode | Photon, Mirror, Fish-Net, Unity Netcode, custom | 200–800h | Netcode is one of the hardest engineering disciplines in games |
| Anti-cheat | Easy Anti-Cheat, BattlEye, VAC, Vanguard, Ricochet | 60–200h | Required for competitive PvP; mobile is harder than PC |
| Voice chat | Vivox, Photon Voice, Discord SDK, AccelByte | 40–120h | Moderation requirements add work |
| Analytics | Unity Analytics, GameAnalytics, deltaDNA, Mixpanel | 40–120h | Game-specific event taxonomy is its own design problem |
| Crash reporting | Unity Cloud Diagnostics, Backtrace, Sentry, Bugsnag | 20–60h | Console crash uploading has platform-specific requirements |
| In-app purchases | Unity IAP, RevenueCat, native StoreKit/Google Play Billing | 60–150h | Receipt validation is non-trivial; subscription handling adds work |
| Ad SDKs | Google AdMob, AppLovin MAX, Unity Ads, ironSource | 60–150h | Mediation, COPPA-safe ad networks for kids' games |
| Community / social | Steam Workshop, Mod.io, Discord integration | 40–200h | UGC opens content moderation and IP questions |
| Live ops platform | LiveOps tools in PlayFab/Beamable, custom | 200–600h | Events, A/B tests, segmentation, remote config |
| Telemetry / cohort analytics | Custom warehouses, Snowflake, BigQuery + dbt | 100–400h | Game economies require custom analytics depth |
| Localization tooling | Lokalise, POEditor, Crowdin, Smartling | 40–100h | Per-language QA and audio recording add significant cost |

## Feature taxonomy (typical modules)

- **Core Gameplay** — controls, mechanics, combat, exploration, puzzles (depends entirely on genre)
- **Progression & Economy** — XP, levels, currencies, loot, crafting, equipment
- **Multiplayer** — matchmaking, lobbies, netcode, party system, voice
- **Social** — friends, guilds/clans, chat, leaderboards, profiles
- **UI / HUD / Menus** — main menu, in-game UI, settings, accessibility options
- **Tutorial & Onboarding** — first-time UX, hints, tooltips
- **Monetization** — store, currencies, IAP, ads, battle pass, subscriptions
- **Live Ops** — events, seasons, daily/weekly content, A/B testing infrastructure
- **Save System** — local, cloud, cross-platform progression
- **Settings & Accessibility** — controls remapping, subtitles, colorblind modes, motion sickness options
- **Customer Support / Reporting** — in-game reporting, ticketing, anti-cheat appeals
- **Admin / LiveOps Dashboard** — content management, player tools, balance tuning, event scheduling

## Recommended features sheet schema

For most game projects, traditional BE/FE/Mobile columns don't fit. Use:

- Engineering — Engine/Gameplay (hours)
- Engineering — Backend / Services (hours)
- Engineering — Tools & Pipeline (hours)
- Content — Art (hours)
- Content — Audio (hours)
- Design (hours)
- QA (hours)
- **Total (hours)**

Content hours often exceed engineering hours for games. Splitting them in the workbook gives the client a realistic picture of where money goes.

For mobile-first casual games or hyper-casual, simpler schema works:
- Engineering (hours)
- Content (Art + Audio) (hours)
- Design (hours)
- **Total (hours)**

## Domain-specific risk register additions

### Risk: Platform certification fails or delays launch

- **Category**: Operational
- **Probability / Impact**: Medium / High
- **Description**: Console (Sony, Microsoft, Nintendo) and store (Apple, Google) certification can take 2–8 weeks and may require rework if technical requirements aren't met. Holiday launch windows can be missed.
- **Mitigation**: Cert requirements documented and tracked from start; pre-cert reviews against TRC/TCR; submission scheduled with buffer; backup launch dates planned.
- **Contingency**: Patch addressing cert findings, expedited resubmit; if launch window critical, soft launch on uncertified platforms first.

### Risk: Netcode reveals scaling or fairness issues at launch

- **Category**: Technical
- **Probability / Impact**: High / High
- **Description**: Multiplayer games routinely launch with server stability or matchmaking issues that hadn't appeared in beta. Refund waves and review damage follow.
- **Mitigation**: Stress testing at expected peak × 3; closed beta with target concurrency; gradual region rollout; queue / wait room infrastructure as fallback.
- **Contingency**: Server capacity expansion plan pre-arranged with cloud provider; rollback plan to previous client version; communications plan for downtime.

### Risk: Live ops content pipeline can't keep up post-launch

- **Category**: Operational
- **Probability / Impact**: High / Medium
- **Description**: Games-as-a-service requires a regular content cadence (weekly/monthly events, seasonal updates). Many studios under-resource the post-launch live ops team and content suffers.
- **Mitigation**: Live ops team scoped during pre-launch; content authoring tools built in MVP, not added later; content cadence committed and resourced before launch; first 6 months of content roadmap pre-built.
- **Contingency**: Reduced cadence with quality maintained; community communication; key creative roles backfilled urgently.

### Risk: Monetization rejection by platform or regulators

- **Category**: Compliance / Commercial
- **Probability / Impact**: Medium / High
- **Description**: Loot box mechanics face regulatory scrutiny in multiple jurisdictions; aggressive monetization patterns can be rejected by Apple/Google. Mid-flight monetization redesign is expensive.
- **Mitigation**: Monetization design reviewed against latest jurisdiction-by-jurisdiction guidance during Discovery; conservative implementation with clear odds disclosure; alternative monetization models designed as fallback.
- **Contingency**: Region-specific monetization variants; cosmetic-only fallback; battle pass model as proven alternative.

### Risk: User-generated content creates moderation overhead and IP exposure

- **Category**: Operational / Legal
- **Probability / Impact**: High / Medium
- **Description**: UGC features (custom levels, mods, shared content) can produce inappropriate content, copyright infringement, or platform policy violations at scale that overwhelms manual moderation.
- **Mitigation**: Automated moderation tooling from launch (image classification, profanity filters, abuse detection); clear ToS and reporting flows; dedicated moderation team scoped; gradual UGC rollout.
- **Contingency**: UGC feature pause if moderation overwhelmed; community managers expanded; AI-assisted moderation (with human review) added.

## AI-assisted productivity profile (overrides for gaming)

- **Engine code (gameplay scripting)** — modest speedup (15–25%); engine-specific patterns require precise correctness; AI sometimes produces almost-correct that doesn't compile/run
- **Backend services (typical web tech)** — substantial speedup (35%+); standard backend patterns
- **Shaders / graphics code** — limited speedup (10–15%); specialized domain, AI training is patchy
- **Asset pipeline tooling** — meaningful speedup (25–30%); scripting work that's well-suited to AI
- **Game design / balancing** — minimal speedup; this is iterative human creative work
- **Content creation (art, audio)** — generative AI can assist (concept art, sound design starting points) but production-grade content still requires human craft
- **Live ops content authoring** — modest speedup if templates and tools are well-designed; otherwise minimal

## Anchor projects (typical scale calibration)

### Anchor: Hyper-casual mobile game, 4-month delivery

- **Scope**: Single-mechanic mobile game, 50+ levels, ad-supported monetization, no multiplayer
- **Total hours**: ~1,200h
- **Total cost** (at $70/h blended): ~$140K
- **Timeline**: 1-month design / playable prototype + 3-month production
- **Notable cost drivers**: Level design at scale, polish iteration, ad SDK integration

### Anchor: Mobile midcore game with live ops, 12-month delivery

- **Scope**: Strategy/RPG with progression systems, asynchronous multiplayer, live events, IAP economy
- **Total hours**: ~6,000h
- **Total cost**: ~$700K–$900K
- **Timeline**: 2-month pre-production + 10-month production
- **Notable cost drivers**: Backend services, live ops infrastructure, art production at scale, balance tuning iteration, soft launch and tuning

### Anchor: Indie PC game (Steam release), 18-month delivery

- **Scope**: Story-driven indie game, single-player, 8–12 hour playthrough, multiple endings
- **Total hours**: ~10,000h
- **Total cost**: ~$1M–$1.4M (often heavily front-loaded with founders working below market)
- **Timeline**: 3-month vertical slice + 15-month production
- **Notable cost drivers**: Art and audio production, narrative writing, voice acting, localization

### Anchor: Competitive multiplayer game with esports potential, 30+ months

- **Scope**: PC/console multiplayer, dedicated server netcode, anti-cheat, ranked play, spectator features
- **Total hours**: ~40,000h+
- **Total cost**: $5M+
- **Timeline**: 6-month preproduction + 24+ month production + indefinite live ops
- **Notable cost drivers**: Netcode engineering (single biggest line), backend services at scale, tournament/esports infrastructure, content production for ongoing seasons

## Common pitfalls in pre-sales for gaming

- "It's like [popular game] but [twist]" — that popular game cost $100M and took 5 years; the comparison rarely helps
- Engineering-only estimates that ignore content production cost — content can be 50–70% of total budget
- Underestimating playtesting and iteration — fun isn't engineered, it's iterated; budget multiple iteration cycles
- Live ops resourcing planned post-launch — the team that builds the game often isn't the team that runs it; transition cost is real
- Localization treated as translation — voice acting, region-specific tuning, per-region QA, censorship adaptations are all real
- Multiplayer added late — netcode shapes architecture; retrofitting is brutal
- Console launch assumed parallel to PC — each platform is a parallel cert track requiring dedicated engineering
- Anti-cheat as afterthought — competitive integrity issues can sink a game; build in from start
- Ratings boards underestimated — ESRB/PEGI submissions take weeks and may require resubmission

## Domain-specific Gate 0 checks

- [ ] Confirm engine choice (Unity, Unreal, Godot, custom) and rationale
- [ ] Identify all target platforms (PC / Mac / Linux / iOS / Android / PS5 / Xbox / Switch / VR)
- [ ] Confirm single-player, multiplayer (sync/async), or both
- [ ] Identify monetization model (premium, F2P with IAP, subscription, ads, hybrid)
- [ ] Confirm live ops scope (one-and-done vs. ongoing service)
- [ ] Identify content production scope (art style, audio scope, narrative depth, localization)
- [ ] Confirm rating target and content constraints (E vs. T vs. M; PEGI levels)
- [ ] Identify UGC scope (mods, custom levels, sharing)
- [ ] Confirm whether competitive integrity / anti-cheat is required
- [ ] Identify launch window and platform certification timeline
