"use client";

import { useState, useEffect } from "react";
import type { FounderProfile } from "@/lib/types";

interface FounderProfileFormProps {
  profile: FounderProfile | null;
  onSave: (data: Partial<FounderProfile>) => void;
}

export default function FounderProfileForm({
  profile,
  onSave,
}: FounderProfileFormProps) {
  const [form, setForm] = useState({
    monthly_burn_rate: 0,
    current_savings: 0,
    runway_floor_months: 3,
    available_hours_per_week_building: 0,
    available_hours_per_week_selling: 0,
    marketing_budget_monthly: 0,
    stop_spend_trigger: "",
    skills: "",
    audiences_familiar_with: "",
  });

  useEffect(() => {
    if (profile) {
      setForm({
        monthly_burn_rate: profile.monthly_burn_rate,
        current_savings: profile.current_savings,
        runway_floor_months: profile.runway_floor_months,
        available_hours_per_week_building: profile.available_hours_per_week_building,
        available_hours_per_week_selling: profile.available_hours_per_week_selling,
        marketing_budget_monthly: profile.marketing_budget_monthly,
        stop_spend_trigger: profile.stop_spend_trigger ?? "",
        skills: (profile.skills ?? []).join(", "),
        audiences_familiar_with: (profile.audiences_familiar_with ?? []).join(", "),
      });
    }
  }, [profile]);

  const runway =
    form.monthly_burn_rate > 0
      ? (form.current_savings / form.monthly_burn_rate).toFixed(1)
      : null;

  const runwayColor = () => {
    if (!runway) return "text-gray-500";
    const months = parseFloat(runway);
    if (months <= 3) return "text-red-400";
    if (months <= 6) return "text-yellow-400";
    return "text-green-400";
  };

  const handleSave = () => {
    const skills = form.skills
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const audiences = form.audiences_familiar_with
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    onSave({
      monthly_burn_rate: form.monthly_burn_rate,
      current_savings: form.current_savings,
      runway_floor_months: form.runway_floor_months,
      available_hours_per_week_building: form.available_hours_per_week_building,
      available_hours_per_week_selling: form.available_hours_per_week_selling,
      marketing_budget_monthly: form.marketing_budget_monthly,
      stop_spend_trigger: form.stop_spend_trigger || null,
      skills: skills.length > 0 ? skills : null,
      audiences_familiar_with: audiences.length > 0 ? audiences : null,
    });
  };

  const numField = (
    label: string,
    key: keyof typeof form,
    opts?: { prefix?: string; step?: number }
  ) => (
    <div>
      <label className="mb-1 block text-xs text-gray-500">{label}</label>
      <div className="flex items-center gap-1">
        {opts?.prefix && <span className="text-sm text-gray-500">{opts.prefix}</span>}
        <input
          type="number"
          value={form[key]}
          step={opts?.step ?? 1}
          onChange={(e) =>
            setForm((prev) => ({ ...prev, [key]: parseFloat(e.target.value) || 0 }))
          }
          className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>
    </div>
  );

  return (
    <div className="max-w-lg space-y-6">
      {/* Runway display */}
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
        <p className="text-xs text-gray-500 uppercase tracking-wider">
          Runway remaining
        </p>
        <p className={`text-3xl font-bold ${runwayColor()}`}>
          {runway ? `${runway} months` : "N/A"}
        </p>
      </div>

      {/* Financial */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-300">Finances</h3>
        {numField("Monthly Burn Rate", "monthly_burn_rate", { prefix: "$" })}
        {numField("Current Savings", "current_savings", { prefix: "$" })}
        {numField("Runway Floor (months)", "runway_floor_months")}
        {numField("Marketing Budget / mo", "marketing_budget_monthly", { prefix: "$" })}
      </div>

      {/* Time */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-300">Time</h3>
        {numField("Hours/week Building", "available_hours_per_week_building")}
        {numField("Hours/week Selling", "available_hours_per_week_selling")}
      </div>

      {/* Skills & Audiences */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-300">
          Skills & Audiences
        </h3>
        <div>
          <label className="mb-1 block text-xs text-gray-500">
            Skills (comma-separated)
          </label>
          <input
            value={form.skills}
            onChange={(e) =>
              setForm((prev) => ({ ...prev, skills: e.target.value }))
            }
            className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="React, Python, Sales"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-500">
            Audiences familiar with (comma-separated)
          </label>
          <input
            value={form.audiences_familiar_with}
            onChange={(e) =>
              setForm((prev) => ({
                ...prev,
                audiences_familiar_with: e.target.value,
              }))
            }
            className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="Indie hackers, SaaS founders"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-500">
            Stop-spend trigger
          </label>
          <input
            value={form.stop_spend_trigger}
            onChange={(e) =>
              setForm((prev) => ({
                ...prev,
                stop_spend_trigger: e.target.value,
              }))
            }
            className="w-full rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="When savings drop below $X"
          />
        </div>
      </div>

      <button
        onClick={handleSave}
        className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
      >
        Save Profile
      </button>
    </div>
  );
}
