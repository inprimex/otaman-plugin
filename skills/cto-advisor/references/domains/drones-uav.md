# Drones / UAV — Strategic Advisory Reference

## What's distinctive about advising in this domain

UAV CTO conversations differ from typical software in that they are hardware-software co-development discussions, not pure software discussions. The strategic question is rarely "what should we build" but "what should we own vs. integrate, and how do regulatory constraints shape the product roadmap." Push back on framings that treat UAV software like a normal product — autopilot integration, ground control software, fleet operations, and certification overhead are real categories of work that need dedicated investment. Civilian/defense crossover requires careful thinking about export controls, customer expectations, and supply chain.

## Vendor landscape

### Flight stacks

- **PX4**: Open-source; modern architecture; strong community; default for serious commercial development
- **ArduPilot**: Open-source; mature; broad platform support; often chosen for fixed-wing / specialty
- **DJI SDK**: Convenient if building on DJI platforms; restrictive licensing; not viable for US government / military
- **Custom flight controllers**: Rare; only justified for specific certification pathways or unique aircraft

### Ground control / mission planning

- **QGroundControl**: PX4-aligned; open-source
- **Mission Planner**: ArduPilot-aligned; open-source
- **Auterion Suite**: Commercial; PX4-based; enterprise focus
- **DroneDeploy, Pix4D Capture**: Commercial mission planning + processing
- **Custom GCS**: Common for differentiated commercial offerings

### Cloud / fleet platforms

- **Auterion Suite**: Full-stack PX4 ecosystem
- **DroneDeploy**: Commercial fleet management
- **AirData**: Logging and analytics
- **AWS / Azure with custom build**: For specific requirements

### Communication / link infrastructure

- **MAVLink** (open standard): Universal across PX4/ArduPilot
- **Microhard, Doodle Labs, Silvus**: RF radio modules
- **Iridium, Inmarsat, ViaSat**: Satellite for BVLOS
- **Cellular modules (Quectel, Sierra Wireless, u-blox)**: 4G/5G uplink

### Computer vision / on-board AI

- **NVIDIA Jetson series**: Default for compute-intensive on-board ML
- **Edge Impulse**: Embedded ML platform
- **OpenMV**: Lower-power vision
- **Specialized SDKs**: From sensor manufacturers (FLIR, Parrot, etc.)

### Sensor manufacturers

- **Cameras**: FLIR (thermal), Sony, Sentera (multispectral), MicaSense (agriculture)
- **LiDAR**: Velodyne, Ouster, Livox, RoboSense
- **GNSS/RTK**: u-blox, Septentrio, NovAtel, Trimble
- **IMU**: Bosch, InvenSense, Analog Devices

### Counter-UAS

- **Detection**: DroneShield, Dedrone, MyDefence, Anduril, Saab Sirius
- **Mitigation**: Highly fragmented, often classified

## Hiring patterns

UAV teams require specialized skills uncommon in pure software:

- **First hire profile**: Senior engineer with combined embedded + flight controls background. Pure software engineers typically struggle without RF / aerospace foundation.
- **Specialized roles**:
  - **Flight controls engineer** — autopilot tuning, control loops, dynamics
  - **RF / SDR engineer** — communications, telemetry, signals work
  - **Embedded firmware engineer** — companion computer, custom hardware
  - **Computer vision engineer** — on-board detection and tracking
  - **Test pilot** — dedicated test pilot or pilot-engineer is common
  - **Regulatory affairs specialist** — FAA / EASA filing expertise
  - **Integration test engineer** — hardware-in-loop, flight test
  - **Manufacturing / hardware engineer** — for custom platforms
- **Outsourcing patterns**: Custom hardware design often outsourced to specialist firms; firmware sometimes outsourced for specific subsystems; flight test typically in-house; regulatory work usually external consultancy + in-house owner.
- **Defense considerations**: Cleared personnel requirements for defense work; ITAR/EAR compliance for export-controlled work; extensive supply chain documentation.

## Common architectural debates

### "Build on existing platform (DJI, Skydio) vs. custom hardware"

Default position for commercial: build on existing platform if mission permits. Custom hardware development adds 2–3 years and millions of dollars to time-to-market.

Flip when: existing platforms can't meet mission requirements; vendor lock-in (especially DJI for US government) is unacceptable; volume justifies custom design economics.

### "PX4 vs. ArduPilot"

Both are mature. PX4 has more modern architecture and stronger commercial backing (Auterion ecosystem). ArduPilot has broader platform support and longer track record.

For new projects in 2026: PX4 is often default unless specific reason favors ArduPilot.

### "Single vehicle vs. swarm architecture"

Swarm operations are dramatically more complex (decentralized planning, comms architecture, deconfliction). Most operations don't need swarm.

Recommend swarm only when mission genuinely requires multi-vehicle coordination; otherwise multiple single vehicles operated together is simpler.

### "BVLOS strategy"

For US commercial: pursue BVLOS waivers via specific use case pathways (Part 108 emerging); operating without BVLOS limits commercial viability for most use cases.

For EU: SORA pathway through Specific Category; longer process but more structured.

For defense: different rules apply; typically more permissive for authorized operations.

### "Civilian vs. defense crossover"

Pure-civilian or pure-defense focus is operationally simpler. Crossover companies must navigate:
- Export controls (ITAR / EAR / dual-use)
- Different customer expectations (defense expects rigor and documentation)
- Supply chain audit requirements
- Cybersecurity standards (defense often demands much stricter)
- Public perception management

If pursuing crossover, design for the harder market (defense) and adapt down for civilian, not the other way around.

## Regulatory bottlenecks

- **Remote ID compliance**: required for US operations; integration is typically days for off-the-shelf modules
- **FAA Part 107 commercial certification**: pilot certification only; not aircraft
- **BVLOS waiver**: 6–18 months typical pathway
- **EASA SORA**: 3–9 months for Specific Category authorization
- **Type certification (passenger UAS)**: 3–7 years; FAA process is nascent
- **DO-178C / DO-254 certification**: per-component; 12–36 months typical
- **Export license (US defense)**: 4–12 weeks per license; longer for novel systems
- **Hardware certification (FCC, CE)**: 8–16 weeks per submission

## Common pitfalls in advisory for UAV

- Treating it as software — UAV is hardware-software co-development requiring different team composition
- Underestimating BVLOS regulatory pathway timelines
- Recommending custom hardware when commercial platforms suffice
- Underestimating field testing cost (weather, sites, pilots, waivers)
- Computer vision quoted from publication metrics not real-world drone footage
- Civilian/defense crossover assumed to be free
- Counter-UAS resistance assumed for free in operating environments where it matters
- DJI SDK lock-in not surfaced (especially relevant for US government / defense customers)
- Vendor closed ecosystem chosen for speed, painful to exit later

## Escalation triggers specific to UAV

- Safety-critical incidents require immediate grounding + investigation + regulator notification
- Regulatory enforcement actions involve legal + executive simultaneously
- Defense contract decisions involve legal (export controls), security (clearances), business simultaneously
- Hardware platform changes affect supply chain, certification, and software architecture
- Counter-UAS / EW work involves additional security clearance and legal considerations
- Operations in conflict zones (relevant for Ukraine and similar contexts) involve duty-of-care, insurance, and possibly defense-classification considerations
- Casualty risk events require comprehensive incident response (operational, legal, communications, regulatory)
