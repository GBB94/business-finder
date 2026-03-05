"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { Idea } from "@/lib/types";

export default function NewIdeaPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: "",
    one_liner: "",
    audience: "",
    problem_statement: "",
    proposed_solution: "",
    offer_ladder_rung: "software",
    target_price_point: "",
    product_use_frequency: "",
    activation_event: "",
    payment_model: "",
    expected_international_pct: "",
  });

  const update = (key: string, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        name: form.name,
        one_liner: form.one_liner,
        audience: form.audience,
        problem_statement: form.problem_statement,
        proposed_solution: form.proposed_solution,
        offer_ladder_rung: form.offer_ladder_rung,
      };
      if (form.target_price_point)
        body.target_price_point = parseFloat(form.target_price_point);
      if (form.product_use_frequency)
        body.product_use_frequency = form.product_use_frequency;
      if (form.activation_event) body.activation_event = form.activation_event;
      if (form.payment_model) body.payment_model = form.payment_model;
      if (form.expected_international_pct)
        body.expected_international_pct = parseInt(form.expected_international_pct);

      const idea = await apiFetch<Idea>("/api/ideas", {
        method: "POST",
        body: JSON.stringify(body),
      });
      router.push(`/ideas/${idea.id}`);
    } catch (err) {
      console.error("Failed to create idea:", err);
      setSaving(false);
    }
  };

  const inputCls =
    "w-full rounded bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500";
  const labelCls = "mb-1 block text-xs text-gray-500";

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="mb-6 text-2xl font-bold">New Idea</h1>
      <form onSubmit={handleSubmit} className="space-y-8">
        {/* Basic Info */}
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
            Basic Info
          </h2>
          <div>
            <label className={labelCls}>Name *</label>
            <input
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
              className={inputCls}
              placeholder="My SaaS idea"
              required
            />
          </div>
          <div>
            <label className={labelCls}>One-liner</label>
            <input
              value={form.one_liner}
              onChange={(e) => update("one_liner", e.target.value)}
              className={inputCls}
              placeholder="A short pitch..."
            />
          </div>
        </section>

        {/* Problem */}
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
            Problem
          </h2>
          <div>
            <label className={labelCls}>Target Audience</label>
            <input
              value={form.audience}
              onChange={(e) => update("audience", e.target.value)}
              className={inputCls}
              placeholder="Who has this problem?"
            />
          </div>
          <div>
            <label className={labelCls}>Problem Statement</label>
            <textarea
              value={form.problem_statement}
              onChange={(e) => update("problem_statement", e.target.value)}
              className={inputCls}
              rows={3}
              placeholder="Describe the pain..."
            />
          </div>
          <div>
            <label className={labelCls}>Proposed Solution</label>
            <textarea
              value={form.proposed_solution}
              onChange={(e) => update("proposed_solution", e.target.value)}
              className={inputCls}
              rows={3}
              placeholder="How will you solve it?"
            />
          </div>
        </section>

        {/* Business Model */}
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
            Business Model
          </h2>
          <div>
            <label className={labelCls}>Offer Type</label>
            <select
              value={form.offer_ladder_rung}
              onChange={(e) => update("offer_ladder_rung", e.target.value)}
              className={inputCls}
            >
              <option value="service">Service</option>
              <option value="productized_service">Productized Service</option>
              <option value="software">Software</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Target Price Point</label>
              <input
                type="number"
                value={form.target_price_point}
                onChange={(e) => update("target_price_point", e.target.value)}
                className={inputCls}
                placeholder="$49/mo"
              />
            </div>
            <div>
              <label className={labelCls}>Use Frequency</label>
              <select
                value={form.product_use_frequency}
                onChange={(e) => update("product_use_frequency", e.target.value)}
                className={inputCls}
              >
                <option value="">Select...</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
              </select>
            </div>
          </div>
          <div>
            <label className={labelCls}>Activation Event</label>
            <input
              value={form.activation_event}
              onChange={(e) => update("activation_event", e.target.value)}
              className={inputCls}
              placeholder="User completes first X..."
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Payment Model</label>
              <select
                value={form.payment_model}
                onChange={(e) => update("payment_model", e.target.value)}
                className={inputCls}
              >
                <option value="">Select...</option>
                <option value="stripe_direct">Stripe Direct</option>
                <option value="paddle_mor">Paddle (MoR)</option>
                <option value="lemonsqueezy_mor">LemonSqueezy (MoR)</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>Int&apos;l Revenue %</label>
              <input
                type="number"
                value={form.expected_international_pct}
                onChange={(e) =>
                  update("expected_international_pct", e.target.value)
                }
                className={inputCls}
                placeholder="0-100"
                min={0}
                max={100}
              />
            </div>
          </div>
        </section>

        <button
          type="submit"
          disabled={saving || !form.name.trim()}
          className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
        >
          {saving ? "Creating..." : "Create Idea"}
        </button>
      </form>
    </div>
  );
}
