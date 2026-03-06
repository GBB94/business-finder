"use client";

import type { Idea } from "@/lib/types";

interface ComplianceFlag {
  key: string;
  label: string;
  severity: "warning" | "info";
  message: string;
}

function evaluateCompliance(idea: Idea): ComplianceFlag[] {
  const flags: ComplianceFlag[] = [];
  const audience = (idea.audience || "").toLowerCase();
  const problem = (idea.problem_statement || "").toLowerCase();
  const solution = (idea.proposed_solution || "").toLowerCase();
  const combined = `${audience} ${problem} ${solution}`;

  // COPPA check — children/minors
  if (/\b(children|kids|minors?|under\s*13|youth|teen)\b/.test(combined)) {
    flags.push({
      key: "coppa",
      label: "COPPA",
      severity: "warning",
      message:
        "Audience may include children under 13. COPPA compliance required — parental consent, data minimization, no behavioral targeting.",
    });
  }

  // HIPAA check — health data
  if (/\b(health|medical|patient|hipaa|clinical|therapy|diagnosis|treatment)\b/.test(combined)) {
    flags.push({
      key: "hipaa",
      label: "HIPAA",
      severity: "warning",
      message:
        "Product may handle protected health information. Evaluate HIPAA applicability — may need BAA, encryption at rest, audit logging.",
    });
  }

  // GDPR check — EU/international
  if (
    /\b(europe|eu|gdpr|international|global|uk|german|french)\b/.test(combined) ||
    (idea.expected_international_pct != null && idea.expected_international_pct > 0)
  ) {
    flags.push({
      key: "gdpr",
      label: "GDPR",
      severity: "warning",
      message:
        "May serve EU users. GDPR requires consent management, data portability, right to erasure, and DPA with processors.",
    });
  }

  // MoR check — high international percentage
  if (idea.expected_international_pct != null && idea.expected_international_pct > 30) {
    flags.push({
      key: "mor",
      label: "Merchant of Record",
      severity: "info",
      message: `International sales estimated at ${idea.expected_international_pct}%. Consider a Merchant of Record (Paddle, LemonSqueezy) to handle international tax compliance.`,
    });
  }

  // Already using Paddle/LemonSqueezy — good
  if (idea.payment_model === "paddle_mor" || idea.payment_model === "lemonsqueezy_mor") {
    flags.push({
      key: "mor_ok",
      label: "MoR Active",
      severity: "info",
      message: "Using a Merchant of Record for payment processing — international tax compliance is handled.",
    });
  }

  // API wrapper risk
  if (/\b(api|wrapper|integration|third.party|scraping|crawl)\b/.test(combined)) {
    flags.push({
      key: "api_tos",
      label: "API ToS",
      severity: "info",
      message:
        "Product may wrap third-party APIs. Review Terms of Service for usage restrictions, rate limits, and commercial use permissions.",
    });
  }

  return flags;
}

interface ComplianceCheckProps {
  idea: Idea;
}

export default function ComplianceCheck({ idea }: ComplianceCheckProps) {
  const flags = evaluateCompliance(idea);

  if (flags.length === 0) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
        <p className="text-xs text-gray-500">No compliance flags detected based on current idea details.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {flags.map((flag) => (
        <div
          key={flag.key}
          className={`rounded-lg border p-3 ${
            flag.severity === "warning"
              ? "border-amber-800 bg-amber-950/20"
              : "border-gray-800 bg-gray-900"
          }`}
        >
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                flag.severity === "warning"
                  ? "bg-amber-900/50 text-amber-400"
                  : "bg-gray-800 text-gray-400"
              }`}
            >
              {flag.label}
            </span>
          </div>
          <p className="text-xs text-gray-400">{flag.message}</p>
        </div>
      ))}
    </div>
  );
}
