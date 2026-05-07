# IoT Domain Expert

## Requirements Checklist (Gate 0 Category 6)

- **Device Types**: Sensors, actuators, gateways, edge computers? Custom hardware or off-the-shelf?
- **Connectivity**: WiFi, BLE, LoRaWAN, Cellular (LTE-M/NB-IoT), Zigbee, Thread/Matter?
- **Scale**: Number of devices (100s, 1000s, millions)? Messages per second? Data volume?
- **Edge Computing**: Processing on device or gateway? ML at edge? Latency requirements?
- **OTA Updates**: Firmware update mechanism? Rollback capability? Update verification?
- **Device Management**: Provisioning, monitoring, configuration, decommissioning?
- **Telemetry**: Data types (temperature, GPS, accelerometer)? Sampling frequency? Retention?
- **Security**: Device authentication? Encrypted communication? Secure boot? Hardware security modules?
- **Cloud Platform**: AWS IoT Core, Azure IoT Hub, GCP IoT Core (deprecated)? Custom MQTT broker?
- **Standards**: Matter/Thread for smart home? OPC-UA for industrial? FHIR for medical devices?

## Compliance Frameworks

- **FDA 21 CFR Part 11**: If medical device. Electronic records, electronic signatures.
- **IEC 62443**: Industrial cybersecurity. Security levels (SL 1-4).
- **ETSI EN 303 645**: Consumer IoT security baseline (EU).
- **FCC/CE**: Radio frequency certification for wireless devices.
- **GDPR**: If devices collect personal data (location, biometrics, behavior patterns).

## Estimation Adjustments

- **Device provisioning system**: 80-160 hours. Zero-touch provisioning, certificate management.
- **OTA update infrastructure**: 60-120 hours. Firmware hosting, differential updates, rollback.
- **Telemetry pipeline**: 80-200 hours. Ingestion, storage, processing, alerting. Scale-dependent.
- **Edge ML**: 120-240 hours. Model optimization (TFLite, ONNX), deployment, monitoring.
- **Hardware-software co-development**: +30-50% if custom hardware. Communication overhead between teams.

## Risk Patterns

- **Device fragmentation**: Multiple hardware versions multiply testing effort.
- **Connectivity reliability**: Intermittent connections require offline-first design, sync conflict resolution.
- **Security vulnerabilities**: Devices in the field are hard to patch. Secure-by-design essential.
- **Scale surprises**: Message volume can spike unexpectedly. Auto-scaling and backpressure needed.
- **Battery life**: Power optimization can require significant firmware rework.
