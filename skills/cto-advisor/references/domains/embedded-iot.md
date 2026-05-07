# Embedded / IoT — Strategic Advisory Reference

## What's distinctive about advising in this domain

Embedded / IoT CTO conversations are dominated by hardware lead times, certification timelines, and the operational reality of devices in the field. The strategic question is rarely "what software should we build" but "how do we operate a fleet at scale, support devices in the field for years, and update them safely." Push back on framings that treat IoT as "an app and a backend with sensors" — firmware development, OTA infrastructure, manufacturing provisioning, and field operations are real categories of work that under-investment in any of them creates years-long pain.

## Vendor landscape

### MCU / SoC platforms

- **Espressif (ESP32 family)**: Default for Wi-Fi/BLE consumer; cost-effective; broad community
- **Nordic (nRF52, nRF53, nRF91)**: Excellent BLE; nRF91 strong for cellular IoT
- **STMicroelectronics (STM32 family)**: Industrial default; broad portfolio
- **NXP**: Industrial / automotive strength
- **Silicon Labs**: Strong in mesh (Zigbee, Thread)
- **Raspberry Pi RP2040 / RP2350**: Hobbyist + light commercial; growing presence
- **NVIDIA Jetson**: When AI inference required at edge

### RTOS / firmware frameworks

- **Zephyr**: Increasingly default for new commercial projects; strong vendor support
- **FreeRTOS** (Amazon-stewarded): Mature; broad MCU support
- **ThreadX (Azure RTOS)**: Microsoft-owned; established
- **NuttX**: Open-source; PX4 uses it
- **Vendor SDKs**: STM32 HAL, NXP MCUXpresso, ESP-IDF (Espressif) — sometimes better for time-to-market on a specific MCU

### Cloud IoT platforms

- **AWS IoT Core**: Mature; broadest service integration; expensive at scale
- **Azure IoT Hub**: Strong for Microsoft-shop customers
- **GCP IoT Core**: **Discontinued in 2023**; migrate if encountered
- **HiveMQ**: Self-managed or cloud; strong MQTT
- **EMQX**: Open-source MQTT broker; commercial offerings
- **balena**: Container-based device management; strong for Linux-class devices

### OTA infrastructure

- **Mender**: Mature; good for Linux devices
- **balena**: OTA + container model
- **AWS IoT Device Management**: Tied to AWS IoT
- **Azure Device Update**: Tied to Azure IoT
- **Memfault**: Observability + OTA; strong on MCU-class devices
- **Custom**: Rarely the right call; reinventing this poorly is dangerous

### Device observability

- **Memfault**: Crash reports, debugging, OTA — purpose-built for embedded
- **Sentry**: Application monitoring, available for embedded
- **Datadog with device telemetry**: For larger orgs

### Connectivity

- **Cellular IoT operators**: 1NCE, Hologram, Twilio Super SIM, Soracom, Onomondo
- **eSIM/iSIM**: Emerging; reduces logistics burden
- **LoRaWAN**: The Things Network (community), Senet, Helium (volatile)
- **Satellite (low-bandwidth)**: Iridium, Swarm (acquired by SpaceX), Astrocast

### Standards bodies / consortiums

- **Matter (CSA)**: Smart home interoperability; getting traction in 2026
- **Thread Group**: Mesh networking standard
- **Bluetooth SIG**: BLE certification
- **Wi-Fi Alliance**: Wi-Fi certification
- **Zigbee Alliance / CSA**: Zigbee certification

## Hiring patterns

- **First hire profile**: Senior firmware engineer with embedded experience plus systems thinking. RTOS + driver experience is non-negotiable for serious commercial work.
- **Specialized roles**:
  - **Firmware engineer** — typically multiple sub-specializations (driver, application, RF)
  - **Hardware engineer** — schematic and PCB; often part-time or fractional at smaller scale
  - **DevOps for embedded** — CI/CD for firmware, hardware-in-loop test automation
  - **OTA / fleet operations engineer** — increasingly its own role at scale
  - **Manufacturing engineer** — factory test, provisioning systems
  - **Cloud / platform engineer** — backend, but with embedded-specific knowledge
  - **Field service engineer** — for industrial / enterprise IoT
  - **RF engineer** — for products with serious wireless requirements
- **Outsourcing patterns**: Hardware design frequently outsourced to design houses; manufacturing always outsourced (CM relationships are strategic); firmware typically in-house once product matters; cloud platform in-house.

## Common architectural debates

### "Linux vs. RTOS vs. bare-metal"

Linux: when you need a full OS (UI, complex networking, container deployment); typically Raspberry Pi class or larger.
RTOS: most common for commercial IoT products; right balance of capability and resource efficiency.
Bare-metal: only for very constrained devices or specific real-time requirements.

Default for new commercial product: RTOS (Zephyr or FreeRTOS).

### "Build OTA infrastructure vs. use Mender / balena / Memfault"

Default position: use existing infrastructure. OTA done wrong bricks fleets; this is one of the highest-stakes pieces of an IoT product to build correctly.

Flip when: very large scale (>1M devices) where vendor pricing exceeds build cost; specific requirements vendors don't support; team has dedicated infrastructure capability.

### "Custom hardware vs. evaluation board / module"

Default position for early stage: evaluation board or pre-certified module (ESP32 module, Nordic module). Custom hardware adds 6–18 months and significant capital.

Flip when: BOM cost dominates at scale and custom design wins; specific form factor requirements; specific certifications easier on custom design.

### "Single platform vs. multi-platform support"

Default position: single hardware platform for MVP. Multi-platform from start multiplies certification, firmware variant management, and support cost.

Flip when: customer base genuinely requires multi-platform; willing to invest in firmware abstraction infrastructure.

### "Wi-Fi vs. cellular vs. LoRa vs. multi-modal"

Wi-Fi: when device is in user-controlled network; provisioning UX is the cost
Cellular: when device must work anywhere; SIM logistics + cost are real
LoRa: long-range, low-power, low-bandwidth; gateway infrastructure required
BLE: short-range, low-power, requires companion device for cloud connection
Mesh (Thread, Zigbee): smart home, when multiple devices coordinate
Multi-modal: increasingly common; more complex but flexible

### "Native cloud (AWS IoT, Azure IoT) vs. multi-cloud abstraction"

Default position: native cloud. The abstraction cost rarely pays off, and switching providers is rare.

Flip when: regulatory or customer requirement for cloud diversity.

## Regulatory bottlenecks

- **FCC certification (US RF)**: 8–16 weeks; failure requires hardware revision
- **CE / RED (EU)**: 8–12 weeks; documentation-heavy
- **Bluetooth qualification**: 4–8 weeks; mandatory for shipping BLE products
- **Matter certification**: 8–16 weeks; test events scheduled
- **Carrier certification (cellular)**: 12–24 weeks for new modules; less if pre-certified
- **UL listing**: 8–24 weeks per class
- **Manufacturing partner onboarding**: 3–9 months
- **EU Cyber Resilience Act preparation (enforcement Dec 2027)**: ongoing; requires architectural and process maturity
- **Hospital / industrial integrations**: customer-by-customer 3–12 months (procurement + IT review)

## Common pitfalls in advisory for embedded/IoT

- Treating it as software project — hardware lead times, manufacturing, certification cycles all real
- Underestimating firmware development effort
- OTA scoped as a checkbox feature — robust OTA is a major investment
- Manufacturing provisioning ignored until production
- Power consumption not modeled until late integration
- BLE pairing UX underestimated — there's no good cross-platform answer
- Component shortages assumed to be over (they're not, in many segments)
- "We'll add cellular later" — adding radio types post-design requires recertification
- Field service costs missed — truck rolls and replacements at scale dominate ops budget
- Data retention and storage cost missed at scale
- EU Cyber Resilience Act treated as 2027 problem — architecture and process changes needed now

## Escalation triggers specific to embedded/IoT

- Manufacturing partner changes are CEO-level decisions (supply chain, IP, quality)
- Product safety incidents (battery thermal events, etc.) require comprehensive response
- OTA failures affecting field devices require crisis response across product, engineering, support
- Major component end-of-life requires hardware revision planning + customer communication
- Regulatory framework changes (CRA, FDA cybersecurity) affect roadmap
- Cybersecurity incidents on connected devices are now regulated events in EU / US healthcare / FCC
- Partnership decisions (Matter joining, Apple Home Kit, etc.) involve business + technical strategy
