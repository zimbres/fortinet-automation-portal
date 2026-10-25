# Fortinet adapter contract and evidence

Official evidence: [Using APIs](https://docs.fortinet.com/document/fortigate/7.2.5/administration-guide/940602/using-apis) documents the address CMDB endpoint and REST API administrator authentication. [Wildcard FQDN addresses](https://docs2.fortinet.com/document/fortigate/7.2.7/administration-guide/217973/using-wildcard-fqdn-addresses-in-firewall-policies) describes wildcard values as FQDN address objects.

The proposed adapter uses bearer Authorization, explicit VDOM, escaped object names, verified HTTPS, no redirects, and no write retries. Address and group paths follow the architecture supplied by the user. Group updates preserve unrelated members through a read/compare/write/read workflow.

No exact FortiOS versions or FNDN reference specification have been supplied. Pagination fields, update payloads, conditional writes, and authoritative reference inspection require validation per supported version. No production write profiles are currently enabled. Reference reports are deliberately incomplete and deletion remains blocked. Simulated tests are not device compatibility evidence.

Orbit discovery was attempted during setup and failed due to DNS access. Public documentation is partial; the full FortiOS API reference is available through FNDN. No maintained organization contract or published mock was found in the empty repository.
