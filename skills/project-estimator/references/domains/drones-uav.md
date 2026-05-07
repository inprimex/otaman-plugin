# Drones / UAV — Estimation Reference

## What's distinctive about this domain

UAV software estimation differs from typical software in three ways: hardware-software integration is the dominant work (autopilot interfaces, sensor fusion, flight control loops aren't rewritten in JavaScript); regulatory regimes vary radically by jurisdiction and use case (Part 107 commercial in US, EASA categories in EU, military or border-crossing operations elsewhere); and safety-critical considerations shape architecture from Day 1 in ways that consumer software never encounters. The most common pre-sales failure is treating drone software as a normal mobile app with a video feed — under-scoping the autopilot integration, telemetry pipeline, ground control software, and certification overhead.

## Compliance frameworks that may apply

| Framework | When it applies | Effort impact |
|---|---|---|
| FAA Part 107 (US) | US commercial operations | minimal in-software; operational compliance rather than code |
| FAA Remote ID | All US drones >250g | +20–60h; broadcast or network-based ID emitter required |
| EASA Open Category (A1/A2/A3) | Most EU recreational/light commercial | minimal direct software cost |
| EASA Specific Category (SORA) | EU operations beyond Open category limits | +200–500h; SORA documentation, MOC compliance |
| EASA Certified Category | Passenger-carrying or high-risk | +1,000h+; full type certification process |
| FAA Type Certification | US passenger UAS / heavy commercial | +1,000h+; multi-year process |
| BVLOS waivers (US) | Beyond visual line of sight | +200–600h depending on pathway (Part 108 emerging) |
| DO-178C | Software in certified avionics | +100–300% on relevant components; full DAL-rated lifecycle |
| DO-254 | Hardware components in certified avionics | +50–200%; hardware design assurance |
| FCC Part 15 / Part 87 | RF transmissions in US | minimal direct software cost; affects radio module choice |
| EU CE (Radio Equipment Directive) | EU sales | minimal software cost; affects hardware certification |
| Export controls (ITAR / EAR US, dual-use EU) | Defense, surveillance, capable platforms | +10–30%; export license process; jurisdiction-aware feature gating |
| MIL-STD-810 / MIL-STD-461 | Military hardware | +30–100% on environmental/EMC compliance |
| Privacy / data protection | Camera-equipped drones, mapping data | +10–20%; geofencing of sensitive areas, data handling |

Ukraine-specific note: civilian/military distinctions matter for both export control compliance and operational deployment. Defense applications in Ukraine require attention to allied export-control regimes (US ITAR/EAR, UK Strategic Export Control, EU Dual-Use) for any hardware/software sourced from those jurisdictions.

## Common integrations and effort patterns

| Integration class | Typical providers | Effort range | Notes |
|---|---|---|---|
| Autopilot / flight controller | PX4, ArduPilot, DJI SDK, custom (rare) | 200–800h | PX4 and ArduPilot are open-source; vendor SDKs are more constrained |
| MAVLink protocol | (open standard) | 80–300h | Standard for ground-air communications; well-documented but version-sensitive |
| RTK GPS / GNSS | u-blox, Septentrio, NovAtel, Trimble | 60–200h | Centimeter-level accuracy for surveying, precision agriculture |
| Companion computer | NVIDIA Jetson, Raspberry Pi 4/5, Intel UP series, custom | 100–400h | On-board compute for vision, ML, complex flight logic |
| Computer vision / detection | OpenCV, YOLO/Ultralytics, NVIDIA DeepStream, custom | 150–500h | Real-time detection on edge hardware |
| LiDAR integration | Velodyne, Ouster, Livox, RoboSense | 100–300h | Point cloud processing is its own subdiscipline |
| Thermal / multispectral cameras | FLIR, MicaSense, Sentera, DJI thermal | 60–150h | Calibration and analysis-specific |
| RF / SDR systems | USRP/Ettus, HackRF, BladeRF, LimeSDR | 200–800h | Custom RF work for telemetry, jamming detection, signals intelligence |
| Cellular communications | Sierra Wireless, Quectel, Telit modules | 80–200h | LTE/5G uplink for BVLOS; network coverage planning |
| Satellite communications | Iridium, Globalstar, Inmarsat | 100–300h | Beyond-LOS-and-cellular; lower bandwidth, higher latency, higher cost |
| Mesh networking | Silvus, Doodle Labs, Persistent Systems | 100–400h | Swarm operations, ground-relay |
| Ground Control Software | QGroundControl, Mission Planner, custom desktop, custom web | 200–800h | Mission planning, telemetry display, command/control UI |
| Cloud platform | AirData, DroneDeploy, Auterion Suite, custom | 200–800h | Fleet management, mission archive, post-flight analysis |
| Mapping / photogrammetry | Pix4D, Agisoft Metashape, OpenDroneMap, WebODM | 100–300h | Image stitching, orthomosaics, 3D models |
| Mission planning | Path planning algorithms (RRT, A*), terrain-aware, no-fly zones | 100–400h | Domain expertise required |
| Geofencing / no-fly zones | Airmap, AirspaceLink, custom datasets | 60–150h | Regulatory data is per-jurisdiction |
| Remote ID emitter | Custom hardware/firmware, off-the-shelf modules | 40–120h | Mandatory in US since 2023 |
| Anti-jam / counter-UAS resistance | Various, often classified | 200–800h | Adaptive frequency hopping, spoofing detection |

## Feature taxonomy (typical modules)

Civilian/commercial UAV system commonly includes:

- **Flight Control Integration** — autopilot interface, command/telemetry, parameter management, firmware updates
- **Mission Planning** — waypoint definition, terrain awareness, no-fly zone checking, simulation
- **Real-time Operations** — telemetry display, video feed, command interface, alerts
- **Sensor Data Pipeline** — camera, LiDAR, RF, thermal capture and storage
- **On-board Processing** — real-time detection, decision logic, edge inference
- **Communications** — RF link, cellular backup, satellite (if applicable), mesh (if swarm)
- **Ground Control Software** — desktop or tablet UI for operators
- **Cloud / Fleet Platform** — multi-vehicle dashboard, mission archive, post-flight analytics
- **Compliance & Safety** — Remote ID, geofencing, return-to-home, fail-safes, logbook
- **Data Processing & Analysis** — photogrammetry, 3D reconstruction, mapping, inspection reports
- **User Management & Roles** — pilot, observer, analyst, admin, regulator-readable logs

Defense / specialized adds:
- **Targeting / Designation** — target acquisition, tracking, designation (often coupled with payload control)
- **Counter-UAS / EW** — RF detection, jamming detection, spoofing resistance, hardening
- **Tactical Communications** — encrypted links, mesh networking, ground-relay, EMCON modes
- **Mission Recording & Debrief** — full-fidelity recording for after-action review
- **Swarm Coordination** — multi-vehicle planning, formation flight, decentralized decisioning

## Recommended features sheet schema

UAV systems span embedded firmware, on-board software, ground software, and cloud — each requires different specialists:

- Firmware / Flight Code (hours)
- On-board Companion Software (hours)
- Ground Control Software (hours)
- Cloud / Backend (hours)
- Web / Mobile UI (hours)
- **Total (hours)**

For purely cloud-side fleet management products (no on-vehicle work), use standard SaaS schema (BE/FE/Mobile).

## Domain-specific risk register additions

### Risk: Regulatory pathway changes mid-project

- **Category**: Regulatory
- **Probability / Impact**: Medium / High
- **Description**: UAV regulations are evolving rapidly (FAA Part 108 emerging, EASA U-space, evolving UTM frameworks). A project scoped against current rules may need rework if rules change.
- **Mitigation**: Regulatory tracking during project; modular design isolating compliance-affected components; relationships with regulators or industry consortia (FAA UPP, EASA initiatives).
- **Contingency**: Operational restriction to currently-permitted use cases; pause new feature work pending clarity; legal review of changed obligations.

### Risk: Hardware availability or vendor lock-in

- **Category**: Commercial / Technical
- **Probability / Impact**: Medium / High
- **Description**: UAV hardware ecosystem is fragmented and vendor-dependent. Component shortages (post-COVID), vendor SDK changes, or geopolitical (DJI restrictions in US government) can disrupt platforms mid-project.
- **Mitigation**: Multi-platform support designed from start where feasible; abstraction layer over vendor SDKs; component-level flexibility (PX4-compatible flight stack rather than vendor-specific); strategic supplier relationships.
- **Contingency**: Migration playbook to alternate platforms; component substitution paths documented; legal review of vendor contract terms for transition periods.

### Risk: BVLOS approval delays defer revenue

- **Category**: Regulatory
- **Probability / Impact**: High / High (for BVLOS-dependent businesses)
- **Description**: Many UAV business models depend on BVLOS operations. Approval pathways are slow (months to years), uncertain, and require operational data the project may not have early.
- **Mitigation**: Discovery includes regulatory pathway analysis with realistic timeline; phased deployment plan that generates revenue under VLOS first; data collection plan to support eventual BVLOS application; consultant engagement with regulator-experienced firms.
- **Contingency**: VLOS-only operations indefinitely with revised business model; trial corridor partnerships; jurisdictional alternatives (some countries/regions are more permissive).

### Risk: Counter-UAS / jamming disrupts operations

- **Category**: Operational
- **Probability / Impact**: Variable by environment / Critical (combat zone) to Low (rural commercial)
- **Description**: Especially relevant for defense or border-area operations: GPS spoofing, RF jamming, and counter-UAS systems can disrupt or destroy UAVs. Civilian jamming incidents also occur (events, sensitive sites).
- **Mitigation**: Robust GNSS integrity (RAIM, multi-constellation, INS backup); frequency-hopping or alternate communication paths; visual / inertial navigation as GPS fallback; hardened firmware against known attack patterns.
- **Contingency**: Return-to-home with degraded navigation; manual recovery protocols; loss replacement budget for high-risk environments.

### Risk: Remote ID compliance gap blocks US operations

- **Category**: Compliance
- **Probability / Impact**: Low / High
- **Description**: FAA Remote ID rule has been in effect since 2023. Non-compliant aircraft cannot operate legally in US national airspace.
- **Mitigation**: Remote ID compliance verified during Discovery; broadcast or network-based emitter integrated; re-verification if aircraft platform changes.
- **Contingency**: Hardware retrofit for older platforms; operational restriction to FAA Recognition Identification Areas (FRIAs) only.

### Risk: Software-flight integration causes airworthiness incident

- **Category**: Safety
- **Probability / Impact**: Low / Catastrophic
- **Description**: Software defects causing loss of control, fly-away, or crash can result in property damage, injury, fatality, regulatory enforcement, and reputational destruction.
- **Mitigation**: Safety-critical design from Day 1; extensive simulation testing; tethered hardware-in-loop testing before flight; flight envelope protection in firmware; pre-flight checks; redundant fail-safe behaviors (RTH, motor cutoff in emergency); incident reporting and learning culture.
- **Contingency**: Incident response plan including grounding all units pending root cause; regulatory notification per Part 107.405 or equivalent; insurance and legal counsel engaged immediately.

## AI-assisted productivity profile (overrides for UAV)

- **Standard ground control / cloud software** — substantial speedup (35%+); regular web/mobile patterns
- **MAVLink protocol handling** — modest speedup (20%); protocol is documented but version-sensitive; verify generated code carefully
- **Computer vision (standard YOLO-style detection)** — meaningful speedup (25–30%); patterns are well-documented; domain calibration still required
- **Custom flight control / autopilot code** — limited speedup (10–15%); safety-critical; domain expertise dominates
- **RF / SDR signal processing** — limited speedup (10–15%); specialized domain, AI training is patchy; verify all generated DSP carefully
- **Real-time embedded firmware** — limited speedup; timing constraints, hardware-specific concerns require human attention
- **Regulatory documentation (SORA, etc.)** — modest speedup (15–25%); structured templates lend themselves to AI assistance; expert review required

## Anchor projects (typical scale calibration)

### Anchor: Cloud-only fleet management SaaS for commercial UAV operators, 4-month delivery

- **Scope**: Multi-tenant web platform, mission archive, telemetry ingestion via standard formats, reporting, no on-vehicle code
- **Total hours**: ~1,400h
- **Total cost** (at $70/h blended): ~$160K
- **Timeline**: 4-week discovery + 3-month development
- **Notable cost drivers**: Telemetry ingestion at scale, multi-format support (different vendor logs), regulatory compliance reporting

### Anchor: Custom GCS + on-board companion software for specific commercial use case (e.g., agriculture, inspection), 6-month delivery

- **Scope**: PX4-based platform, custom mission planning UI, real-time on-board processing, post-flight analysis pipeline
- **Total hours**: ~2,500h
- **Total cost**: ~$300K–$400K
- **Timeline**: 6-week discovery + 5-month development
- **Notable cost drivers**: Companion computer integration, sensor calibration, GCS development, processing pipeline, field testing iteration

### Anchor: Defense / tactical UAV system, 12-month+ delivery

- **Scope**: Custom hardware + software stack, encrypted communications, hardening, operator training, certification
- **Total hours**: 8,000h+
- **Total cost**: $1M+
- **Timeline**: 12+ months including hardware development cycles
- **Notable cost drivers**: Custom firmware, RF / EW work, hardening, certification, field trials, training; ranges very widely with platform complexity and threat environment

### Anchor: Counter-UAS detection system, 9-month delivery

- **Scope**: RF-based detection, classification, alerting; integration with response systems
- **Total hours**: ~3,500h
- **Total cost**: ~$450K–$650K
- **Timeline**: 8-week discovery + 7-month development
- **Notable cost drivers**: SDR signal processing (often the dominant work), classification algorithms, real-time processing infrastructure, integration with effector systems

## Common pitfalls in pre-sales for UAV

- "Like a DJI but with our features" — DJI's vertical integration represents thousands of person-years; building "DJI-like" capability is rarely viable
- Underestimating field testing cost — flight time, weather windows, test sites, pilots, FAA waivers all add weeks or months
- Treating it as a software project — UAV work is hardware-software co-development; pure-software companies often struggle without RF/embedded expertise
- BVLOS scoped without regulatory pathway analysis — "we'll fly BVLOS" without an approved waiver pathway is a deal-killer disclosed too late
- Counter-UAS resistance assumed for free — robust operations in contested environments require explicit hardening work
- Defense/civilian crossover assumed — defense customers expect TEMPEST-level rigor, supply chain documentation, ITAR awareness; civilian projects can't cost-effectively deliver this without scope inflation
- Computer vision quoted from publication metrics — research benchmarks rarely reflect real-world drone footage performance (motion, varying lighting, occlusion)
- Regulatory documentation effort underestimated — SORA, type certification, BVLOS waivers each require hundreds of hours of structured documentation
- Vendor SDK lock-in not surfaced — DJI SDK restrictions (especially for US government / military use) often surprise clients

## Domain-specific Gate 0 checks

- [ ] Identify use case category (commercial inspection / agriculture / mapping / delivery / passenger / defense / counter-UAS / hobbyist platform)
- [ ] Confirm operating jurisdictions (each has own regulator)
- [ ] Identify VLOS / EVLOS / BVLOS operational requirement
- [ ] Confirm flight platform (existing vendor, custom, multiple)
- [ ] Identify Remote ID compliance need (US, EU CE, others)
- [ ] Identify communication architecture (RF only, RF+cellular, satellite, mesh)
- [ ] Confirm export control sensitivity (ITAR/EAR/dual-use; relevant for client and project geography)
- [ ] Identify safety-critical aspects (passenger-carrying, urban operations, near critical infrastructure)
- [ ] Confirm certification scope (Part 107 only, BVLOS waiver, type cert, DO-178C component)
- [ ] Identify on-board compute scope (none, modest, substantial AI/CV inference)
