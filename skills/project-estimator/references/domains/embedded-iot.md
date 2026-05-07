# Embedded / IoT — Estimation Reference

## What's distinctive about this domain

Embedded and IoT estimation differs from typical software in that the constraints are real and unforgiving: memory, power, bandwidth, real-time deadlines, and physical operating conditions all bound what's possible. Hardware lead times (12–52 weeks for components in current supply chains) and certification cycles (FCC, CE, RED, regional safety) shape the project schedule as much as engineering effort. The most common pre-sales failure is treating an IoT project as "an app and a backend with some sensors" — under-scoping firmware development, OTA infrastructure, device fleet management, and the long tail of edge cases that emerge with hundreds or thousands of devices in the field.

## Compliance frameworks that may apply

| Framework | When it applies | Effort impact |
|---|---|---|
| FCC Part 15 (US) | Any RF-emitting device sold in US | minimal software cost; affects hardware/firmware design |
| FCC Part 18 / Part 95 | Industrial, scientific, medical / personal radio | varies by class |
| CE / RED (EU) | Any electronic device sold in EU | minimal software cost; documentation overhead |
| UKCA (UK) | Any electronic device sold in UK | similar to CE; mostly documentation |
| ETSI EN 303 645 | EU consumer IoT cybersecurity baseline | +20–40h documentation; affects design choices |
| EU Cyber Resilience Act (2027 enforcement) | All connected products in EU | +40–150h; vulnerability handling, SBOM, secure-by-default |
| FCC ID for Wi-Fi/BLE/LTE modules | Modules need certification | minimal if using pre-certified modules |
| RoHS / REACH | EU material restrictions | minimal software impact; affects component selection |
| Matter (formerly CHIP) | Smart home interoperability | +200–500h; certification process; protocol stack |
| Zigbee Alliance / CSA certification | Zigbee devices | +100–250h; certification fees |
| Bluetooth SIG qualification | BLE devices | +60–150h; declaration process |
| GDPR / ePrivacy | EU users, devices collecting personal data | +10–20%; device-side and platform-side |
| HIPAA | Medical devices, hospital equipment | see healthcare.md; significant implications |
| FDA pre-market | Connected medical devices | see healthcare.md FDA notes |
| UL listing | Safety-critical devices in US | +50–200h; per-class effort varies |
| IEC 62443 | Industrial control systems cybersecurity | +30–80%; significant on automation/OT projects |

EU Cyber Resilience Act is the most significant near-term regulatory development for IoT; enforcement starts December 2027 and applies to virtually all connected products sold in EU. Build secure-by-default and lifecycle vulnerability handling into the architecture now, not as a 2027 retrofit.

## Common integrations and effort patterns

| Integration class | Typical providers | Effort range | Notes |
|---|---|---|---|
| RTOS | FreeRTOS, Zephyr, ThreadX, NuttX, custom | 80–250h | Zephyr is increasingly the default for new projects |
| Bare-metal frameworks | STM32 HAL, NXP SDK, Espressif IDF | 40–150h | Vendor-specific; familiarity matters |
| Communication — Wi-Fi | ESP32 (built-in), Atheros/Qualcomm, Cypress | 60–200h | Wi-Fi provisioning UX is a frequent pain point |
| Communication — BLE | Nordic nRF52/53, ESP32, Silicon Labs | 80–250h | BLE pairing flows, GATT design, multi-platform mobile support |
| Communication — Cellular (LTE-M, NB-IoT, 4G/5G) | Quectel, Sierra Wireless, u-blox, Nordic nRF91 | 100–300h | Carrier certification, eSIM/iSIM, battery consumption |
| Communication — LoRaWAN | Semtech radios, The Things Network, Helium | 80–250h | Long-range low-power; gateway infrastructure |
| Communication — Mesh | Thread, Zigbee, Matter, OpenThread | 100–400h | Standards-based mesh; certification overhead |
| Cloud IoT platform | AWS IoT Core, Azure IoT Hub, GCP IoT Core (deprecated 2023), HiveMQ | 100–400h | Device identity, messaging, twin/shadow, fleet ops |
| MQTT broker | Eclipse Mosquitto, HiveMQ, EMQX, custom | 60–200h | Self-hosted vs managed; security topology |
| Device provisioning | AWS IoT JITP/JITR, Azure Device Provisioning, custom | 100–250h | Zero-touch provisioning is a real engineering challenge |
| OTA firmware update | Mender, balena, ESP-IDF native, custom AWS IoT/Azure | 100–400h | OTA done wrong bricks fleets; this deserves serious investment |
| Device fleet management | balena, Memfault, AWS IoT Device Management, custom | 100–300h | Visibility, debugging, remote diagnostics |
| Edge ML inference | TensorFlow Lite, ONNX Runtime, Edge Impulse, NVIDIA Jetson stack | 80–300h | Constrained device inference is its own discipline |
| Time-series database | InfluxDB, TimescaleDB, AWS Timestream, ClickHouse | 60–200h | Sensor data at scale needs purpose-built storage |
| IoT-specific analytics | Tinybird, Grafana, custom | 60–200h | Real-time dashboards over device fleets |
| Mobile companion apps | iOS/Android with BLE, often React Native or native | 200–500h | Platform-specific BLE behavior is a known pain |
| Voice assistant integration | Alexa, Google Home, Apple HomeKit, Matter (universal) | 80–250h per platform | Each platform has its own SDK, certification |

## Feature taxonomy (typical modules)

- **Firmware Core** — main loop, RTOS configuration, low-power management, watchdog, fault handling
- **Drivers** — peripheral drivers (sensors, actuators, displays, communication chips)
- **Communication Stack** — protocol implementation (Wi-Fi, BLE, cellular, mesh, MQTT, etc.)
- **Security** — secure boot, encryption keys, attestation, secure storage
- **OTA Update** — partition management, dual-bank, rollback, signed firmware
- **Sensor Data Pipeline** — sampling, filtering, aggregation, transmission
- **Local Processing / ML** — on-device inference, anomaly detection, decision logic
- **Provisioning** — first-boot setup, network credentials, cloud enrollment
- **Cloud Backend** — device identity, messaging routing, command dispatch, twin/shadow state
- **Fleet Management** — device inventory, health monitoring, remote diagnostics, OTA orchestration
- **Mobile / Web App** — user interface for device control, data viewing, configuration
- **Admin / Operations Tools** — fleet ops dashboard, alerting, support tools
- **Manufacturing Provisioning** — factory test fixtures, per-device cryptographic identity, calibration

## Recommended features sheet schema

For embedded/IoT projects, multiple specializations are involved:

- Firmware (hours)
- Cloud Backend (hours)
- Mobile App (hours)
- Web Admin (hours)
- Manufacturing / Test (hours)
- **Total (hours)**

Manufacturing provisioning is consistently underscoped in pre-sales — it's not glamorous work but per-device factory testing and identity provisioning is necessary for any shipped product.

## Domain-specific risk register additions

### Risk: OTA bricks production fleet

- **Category**: Operational
- **Probability / Impact**: Low / Critical
- **Description**: A botched OTA update can render thousands of deployed devices unusable. Field recovery (truck rolls or replacements) can be 100× the cost of the update itself, plus customer trust damage.
- **Mitigation**: Dual-bank firmware with automatic rollback on boot failure; staged rollout (canary, then 1%, then 10%, etc.); cryptographic signing; pre-deployment hardware-in-loop testing; emergency stop capability for in-flight rollouts; comprehensive update telemetry.
- **Contingency**: Field service team activation; physical recovery procedure for affected units; customer communication and remediation; root cause and process improvement.

### Risk: Component shortage delays production

- **Category**: Commercial
- **Probability / Impact**: High / High
- **Description**: Semiconductor shortages persist in some segments. Lead times of 26–52 weeks for specific MCUs, sensors, or radio modules can delay product launch indefinitely.
- **Mitigation**: Component selection review during Discovery for current availability and supply diversification; second-source qualification for critical components; strategic inventory commitments (when financially viable); design for substitutability (pin-compatible alternates).
- **Contingency**: Component swap with software adaptation; redesign for alternate component class; production delay with customer communication.

### Risk: Field debugging is impossible without dedicated remote diagnostics

- **Category**: Operational
- **Probability / Impact**: High / Medium
- **Description**: When devices fail in the field, "send a debugger" isn't an option. Without proper telemetry, fault reporting, and remote diagnostics from Day 1, customer support becomes impossible at scale.
- **Mitigation**: Memfault, Sentry, or similar device-side error reporting integrated from MVP; structured logging with cloud aggregation; remote access capability for select diagnostic scenarios; coredump capture and upload.
- **Contingency**: Field engineer dispatch budget; customer device replacement program; root cause analysis on returned units.

### Risk: Power consumption exceeds battery/budget

- **Category**: Technical
- **Probability / Impact**: High / High (battery-powered devices) / Medium (mains-powered)
- **Description**: Battery life targets routinely missed because power profile not modeled until late integration. Once hardware is fixed, software optimization has limits.
- **Mitigation**: Power budget analysis during Discovery; profiling on real hardware as soon as available; deep sleep architecture from initial firmware design; communication batching strategy; OTA mode considerations.
- **Contingency**: Larger battery in next hardware revision; reduced functionality battery-saver mode; communication frequency reduction.

### Risk: Manufacturing yield and per-device variance

- **Category**: Operational
- **Probability / Impact**: Medium / Medium
- **Description**: Production yields below 95% are common in early manufacturing runs. Per-device calibration, sensor variance, and assembly defects all surface at scale.
- **Mitigation**: Manufacturing test fixture and software co-developed with product; DFM review with manufacturing partner; per-device calibration data captured and stored; pilot run before scale production.
- **Contingency**: Failed-unit analysis pipeline; calibration-data-based software compensation; manufacturing partner change if quality issues persist.

### Risk: Regulatory certification fails or delays

- **Category**: Compliance
- **Probability / Impact**: Medium / High
- **Description**: FCC, CE, RED, BLE qualification, or similar testing fails — usually for spurious emissions, battery safety, or interference. Recertification adds weeks-months.
- **Mitigation**: Pre-certification testing at experienced lab during prototype phase; experienced compliance partner engaged early; design margin against limits; review of similar products' certification reports.
- **Contingency**: Hardware revision and recertification; market launch delay with customer/distribution communication.

## AI-assisted productivity profile (overrides for embedded/IoT)

- **Cloud backend / mobile / web** — substantial speedup (35%+); standard patterns
- **Standard driver code (well-known peripherals)** — meaningful speedup (25–30%); patterns are documented
- **Custom firmware / RTOS application logic** — limited speedup (15–20%); real-time and resource constraints require careful verification
- **Bit-level protocol implementation** — limited speedup; subtle errors are easy to introduce
- **Power optimization** — minimal speedup; this is empirical measurement and iteration
- **OTA infrastructure** — modest speedup (15–25%); patterns exist but criticality demands review
- **Manufacturing test / provisioning** — modest speedup (15–25%); domain-specific
- **Hardware bring-up / debugging** — minimal AI speedup; requires hands-on hardware work

## Anchor projects (typical scale calibration)

### Anchor: Connected consumer device (smart-home category), 9-month delivery

- **Scope**: Custom hardware (ESP32 or similar) with mobile companion app, cloud backend, BLE provisioning, OTA, basic admin
- **Total hours**: ~3,000h
- **Total cost** (at $70/h blended): ~$340K
- **Timeline**: 2-month design + 7-month development including hardware iteration
- **Notable cost drivers**: Hardware bring-up cycles, mobile BLE work, OTA infrastructure, certification (FCC, CE), manufacturing partnership

### Anchor: Industrial sensor network with cloud platform, 12-month delivery

- **Scope**: Custom firmware on sensor nodes (LoRaWAN or cellular), gateway software, cloud platform with analytics, web dashboard, fleet management
- **Total hours**: ~5,000h
- **Total cost**: ~$550K–$700K
- **Timeline**: 3-month design + 9-month development
- **Notable cost drivers**: Field testing across deployment scenarios, gateway software, cloud architecture for time-series at scale, dashboard and analytics

### Anchor: Connected medical device (Class II), 18-month delivery

- **Scope**: FDA-cleared connected device, mobile app, cloud platform, all with appropriate medical software lifecycle compliance
- **Total hours**: ~10,000h+
- **Total cost**: $1.2M+
- **Timeline**: 4-month design + 14-month development including V&V, regulatory submission
- **Notable cost drivers**: IEC 62304 lifecycle compliance (~30% of total), FDA submission preparation, clinical validation, cybersecurity (FDA premarket guidance), HIPAA compliance

### Anchor: Smart home Matter device, 12-month delivery

- **Scope**: Matter-certified device with companion app, cloud account features, multi-ecosystem (Apple/Google/Amazon/Samsung) interoperability
- **Total hours**: ~4,500h
- **Total cost**: ~$500K–$650K
- **Timeline**: 3-month design + 9-month development
- **Notable cost drivers**: Matter certification, Thread/Wi-Fi commissioning, multi-ecosystem testing, mobile app for setup

## Common pitfalls in pre-sales for embedded/IoT

- "Just like Nest but for X" — Nest's OTA, manufacturing, and field operations represent years of investment beyond visible product
- Underestimating firmware development — "it's just C, how hard can it be" misses RTOS, hardware bring-up, peripheral driver work, debugging on resource-constrained targets
- OTA scoped as a checkbox feature — robust OTA is one of the hardest pieces of an IoT product to build correctly; deserves dedicated investment
- Manufacturing provisioning ignored — every device needs unique identity, calibration, factory test; not a Day-One thought but should be
- Certification scoped as a line item rather than a critical path — FCC/CE timelines are long and not parallelizable with launch prep
- "We'll add LTE later" — adding cellular to a device originally Wi-Fi or BLE only requires hardware revision and recertification
- BLE pairing UX underestimated — there's no good cross-platform BLE pairing UX; expect significant work on iOS/Android idiosyncrasies
- Field upgradability assumed for free — without thoughtful firmware architecture, upgrade paths can become impossible
- Component selection deferred to manufacturing partner — software architecture depends on chip choice; coordinate early
- Data retention requirements fuzzy — IoT products generate huge volumes; storage costs escalate without explicit retention policies

## Domain-specific Gate 0 checks

- [ ] Confirm device class (consumer / industrial / medical / automotive / defense / agricultural)
- [ ] Identify communication architecture (Wi-Fi / BLE / cellular / LoRa / mesh / multi-modal)
- [ ] Identify hardware status (existing platform / custom design / ODM partnership)
- [ ] Confirm power source (mains / rechargeable / primary battery / energy harvesting)
- [ ] Identify deployment environment (controlled indoor / outdoor / harsh / safety-critical)
- [ ] Confirm regulatory scope (regions, classes, specific frameworks like Matter or HIPAA)
- [ ] Identify scale targets (units in field at year 1, year 3) — drives architecture
- [ ] Confirm OTA and remote management requirements
- [ ] Identify manufacturing partner and provisioning approach
- [ ] Confirm cloud platform preference / constraint
- [ ] Identify fleet management and observability requirements
