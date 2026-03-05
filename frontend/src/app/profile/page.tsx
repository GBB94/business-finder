"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { FounderProfile } from "@/lib/types";
import FounderProfileForm from "@/components/FounderProfileForm";

export default function ProfilePage() {
  const [profile, setProfile] = useState<FounderProfile | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiFetch<FounderProfile>("/api/profile")
      .then(setProfile)
      .catch((err) => console.error("Failed to load profile:", err));
  }, []);

  const handleSave = async (data: Partial<FounderProfile>) => {
    try {
      const updated = await apiFetch<FounderProfile>("/api/profile", {
        method: "PUT",
        body: JSON.stringify(data),
      });
      setProfile(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      console.error("Failed to save profile:", err);
    }
  };

  return (
    <div className="p-6">
      <h1 className="mb-6 text-2xl font-bold">Founder Profile</h1>
      {saved && (
        <div className="mb-4 rounded-lg border border-green-800 bg-green-950/30 px-3 py-2 text-sm text-green-400">
          Profile saved
        </div>
      )}
      <FounderProfileForm profile={profile} onSave={handleSave} />
    </div>
  );
}
