"""Resolve Aiven Kafka connection settings from the environment.

Two naming conventions are accepted:

* ``AIVEN_KAFKA_*`` — the project's own variables (file-based TLS or SASL).
* ``KAFKA_*`` — the variables Aiven Runtime injects for an integrated Kafka
  service: ``KAFKA_BOOTSTRAP_SERVERS``, ``KAFKA_SECURITY_PROTOCOL``,
  ``KAFKA_ACCESS_KEY``, ``KAFKA_ACCESS_CERT`` and ``KAFKA_CA_CERT``, where the
  last three hold inline PEM text rather than file paths.

Secrets never leave this module except inside the librdkafka config dict.
``describe()`` is the only thing health endpoints and preflights should print.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

SECURE_PROTOCOLS = frozenset({"SSL", "SASL_SSL"})
DEFAULT_CLIENT_ID = "disruptors-dependency"
DEFAULT_CONSUMER_GROUP = "dependency-incident-orchestrator"


def _env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return ""


def _env_pem(*names: str) -> str:
    """Inline PEM may arrive with literal ``\\n`` sequences from secret stores."""
    value = _env(*names)
    return value.replace("\\n", "\n") if value else ""


@dataclass(frozen=True)
class KafkaSettings:
    brokers: str
    security_protocol: str
    client_id: str
    source: str
    ca_file: str = ""
    cert_file: str = ""
    key_file: str = ""
    ca_pem: str = field(default="", repr=False)
    cert_pem: str = field(default="", repr=False)
    key_pem: str = field(default="", repr=False)
    sasl_mechanism: str = ""
    sasl_username: str = field(default="", repr=False)
    sasl_password: str = field(default="", repr=False)
    allow_plaintext: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.brokers)

    @property
    def uses_mtls(self) -> bool:
        return bool((self.cert_file and self.key_file) or (self.cert_pem and self.key_pem))

    @property
    def uses_sasl(self) -> bool:
        return bool(self.sasl_username and self.sasl_password)

    @property
    def auth_method(self) -> str:
        if self.uses_sasl:
            return "SASL"
        if self.uses_mtls:
            return "MTLS"
        return "NONE"

    def validate(self) -> list[str]:
        """Return human-readable problems; empty list means usable."""
        problems: list[str] = []
        if not self.brokers:
            problems.append("No Kafka bootstrap servers configured.")
            return problems
        if self.security_protocol not in SECURE_PROTOCOLS and not self.allow_plaintext:
            problems.append(
                f"Security protocol {self.security_protocol} is not TLS; "
                "set AIVEN_KAFKA_ALLOW_PLAINTEXT=true only for a local broker."
            )
        if bool(self.sasl_username) != bool(self.sasl_password):
            problems.append("SASL username and password must both be set.")
        if bool(self.cert_file) != bool(self.key_file):
            problems.append("Client certificate and key files must both be set.")
        if bool(self.cert_pem) != bool(self.key_pem):
            problems.append("Inline client certificate and key must both be set.")
        if self.security_protocol in SECURE_PROTOCOLS and self.auth_method == "NONE":
            problems.append("TLS is enabled but neither mTLS nor SASL credentials are set.")
        if self.uses_sasl and self.security_protocol == "SSL":
            problems.append("SASL credentials require AIVEN_KAFKA_SECURITY_PROTOCOL=SASL_SSL.")
        if self.security_protocol == "SASL_SSL" and not self.uses_sasl:
            problems.append("SASL_SSL requires a username and password.")
        if self.security_protocol in SECURE_PROTOCOLS and not (self.ca_file or self.ca_pem):
            problems.append("No CA certificate; Aiven brokers use a private CA.")
        for label, path in (("CA", self.ca_file), ("certificate", self.cert_file),
                            ("key", self.key_file)):
            if path and not os.path.isfile(path):
                problems.append(f"Configured {label} file does not exist at the given path.")
        return problems

    def librdkafka(self) -> dict:
        """Base producer/consumer config. Contains secrets; never log it."""
        problems = self.validate()
        if problems:
            raise RuntimeError("Kafka configuration invalid: " + " ".join(problems))
        config = {
            "bootstrap.servers": self.brokers,
            "client.id": self.client_id,
            "security.protocol": self.security_protocol,
        }
        if self.ca_file:
            config["ssl.ca.location"] = self.ca_file
        elif self.ca_pem:
            config["ssl.ca.pem"] = self.ca_pem
        if self.cert_file and self.key_file:
            config["ssl.certificate.location"] = self.cert_file
            config["ssl.key.location"] = self.key_file
        elif self.cert_pem and self.key_pem:
            config["ssl.certificate.pem"] = self.cert_pem
            config["ssl.key.pem"] = self.key_pem
        if self.uses_sasl:
            config["sasl.mechanism"] = self.sasl_mechanism or "PLAIN"
            config["sasl.username"] = self.sasl_username
            config["sasl.password"] = self.sasl_password
        return config

    def describe(self) -> dict:
        """Secret-free summary safe for health endpoints and logs."""
        problems = self.validate()
        return {
            "configured": self.configured,
            "source": self.source,
            "security_protocol": self.security_protocol if self.configured else None,
            "auth_method": self.auth_method if self.configured else None,
            "ca_provided": bool(self.ca_file or self.ca_pem),
            "credential_format": (
                "file" if (self.cert_file or self.ca_file)
                else "inline_pem" if (self.cert_pem or self.ca_pem)
                else None
            ),
            "broker_count": len([b for b in self.brokers.split(",") if b.strip()]),
            "client_id": self.client_id,
            "valid": self.configured and not problems,
            "problems": problems,
        }


def load_kafka_settings() -> KafkaSettings:
    brokers = _env("AIVEN_KAFKA_BROKERS")
    source = "AIVEN_KAFKA_BROKERS"
    if not brokers:
        brokers = _env("KAFKA_BOOTSTRAP_SERVERS")
        source = "KAFKA_BOOTSTRAP_SERVERS" if brokers else "NONE"

    sasl_username = _env("AIVEN_KAFKA_USERNAME", "KAFKA_SASL_USERNAME")
    sasl_password = _env("AIVEN_KAFKA_PASSWORD", "KAFKA_SASL_PASSWORD")
    protocol = _env("AIVEN_KAFKA_SECURITY_PROTOCOL", "KAFKA_SECURITY_PROTOCOL").upper()
    if not protocol:
        protocol = "SASL_SSL" if (sasl_username and sasl_password) else "SSL"

    return KafkaSettings(
        brokers=brokers,
        security_protocol=protocol,
        client_id=_env("AIVEN_KAFKA_CLIENT_ID") or DEFAULT_CLIENT_ID,
        source=source,
        ca_file=_env("AIVEN_KAFKA_CA_FILE"),
        cert_file=_env("AIVEN_KAFKA_CERT_FILE"),
        key_file=_env("AIVEN_KAFKA_KEY_FILE"),
        ca_pem=_env_pem("AIVEN_KAFKA_CA_PEM", "KAFKA_CA_CERT"),
        cert_pem=_env_pem("AIVEN_KAFKA_CERT_PEM", "KAFKA_ACCESS_CERT"),
        key_pem=_env_pem("AIVEN_KAFKA_KEY_PEM", "KAFKA_ACCESS_KEY"),
        sasl_mechanism=_env("AIVEN_KAFKA_SASL_MECHANISM", "KAFKA_SASL_MECHANISM").upper(),
        sasl_username=sasl_username,
        sasl_password=sasl_password,
        allow_plaintext=_env("AIVEN_KAFKA_ALLOW_PLAINTEXT").lower() in {"1", "true", "yes"},
    )


def consumer_group() -> str:
    return _env("AIVEN_KAFKA_CONSUMER_GROUP") or DEFAULT_CONSUMER_GROUP
