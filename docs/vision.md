# PharmaForge — Long-Term Vision

> **Status:** This document preserves the original enterprise positioning and
> long-term product vision. The product currently ships as a focused DSCSA
> compliance tool for independent pharmacies (see the [README](../README.md)).
> The enterprise modules below still exist in the codebase and can be enabled
> with the `VITE_ENTERPRISE_FEATURES` flag.

## Operating System for Virtual Pharma

The long-term ambition for PharmaForge is an enterprise supply chain,
compliance, and regulatory intelligence platform for pharmaceutical
companies — a single operating system covering sourcing, risk, and
regulatory workflows.

## Enterprise Modules

### 🔭 Supply Chain Watchtower
- Real-time FDA enforcement monitoring
- Vendor risk scoring (0-100)
- Automated alert generation
- Multi-factor risk analysis

### 🤖 Regulatory Copilot
- RAG-powered Q&A
- FDA guidance document search
- Source citation tracking
- Auto-draft email generation

### 💼 War Council
- Multi-persona analysis (Regulatory, Legal, Supply Chain)
- Risk assessment synthesis
- Priority action recommendations

### 🛒 Smart Sourcing SDR
- AI-generated RFQ emails
- Multi-vendor comparison
- Automated scoring algorithms
- Admin approval workflow

### 📜 DSCSA / EPCIS Compliance
- JSON/XML EPCIS validation
- Chain-of-custody verification
- Compliance issue detection
- Audit packet generation

*(This module is the core of the current pharmacy-focused product.)*

### 📊 Audit & Compliance
- Immutable activity logging
- Filterable audit trails
- CSV export for regulators
- Real-time activity monitoring

## Roadmap Ideas

- Kubernetes deployment support
- Multi-region deployment
- Advanced analytics dashboards
- Mobile app (React Native)
- API rate limiting tiers
- SSO/SAML integration
- Advanced ML models
- Real-time collaboration

## Why the Pivot to Pharmacies First

The FDA small-dispenser exemption (dispensers with 25 or fewer full-time
pharmacists and pharmacy technicians) ends **November 27, 2026**. Independent
pharmacies need a simple, affordable way to receive, validate, and store
EPCIS data before that date. The DSCSA/EPCIS engine — the most mature part
of the platform — serves that need directly, so the product leads with it.

The enterprise surface is feature-flagged, not deleted; the vision above
remains the long-term direction.
