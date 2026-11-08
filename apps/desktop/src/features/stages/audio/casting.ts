export interface Voice { id: string; name: string; gender?: string }

export interface Castable { character_id?: string; canonical_name: string; gender?: string }

export type Casting = Record<string, string>;

const NARRATOR_KEYS = ["narrator", "NARRATOR", "The_Narrator"] as const;

/** The voices of the engine's primary speech provider. The id is what the engine looks a voice up by. */
export function voicesFromProviders(res: { primary_provider: string; providers: Array<{ id: string; voices?: any[] }> } | null | undefined): Voice[] {
  const provider = res?.providers?.find((p) => p.id === res.primary_provider);
  const seen = new Set<string>();
  const out: Voice[] = [];
  for (const raw of provider?.voices ?? []) {
    if (typeof raw !== "object" || raw === null) continue;
    const id = typeof raw.id === "string" && raw.id ? raw.id : typeof raw.name === "string" ? raw.name : "";
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push({ id, name: typeof raw.name === "string" && raw.name ? raw.name : id, gender: typeof raw.gender === "string" ? raw.gender : undefined });
  }
  return out;
}

/** A character is cast under its id and under its name, because the engine may refer to either. */
export function castKeys(character: Castable): string[] {
  return [...new Set([character.character_id, character.canonical_name].filter((k): k is string => Boolean(k)))];
}

export function castingValue(casting: Casting, character: Castable): string {
  for (const key of castKeys(character)) if (casting[key]) return casting[key];
  return "";
}

/**
 * Give every character that has no voice yet one of the engine's voices. The choice depends only on the order of the
 * characters, their gender when it is known, and the order of the voices, never on a name. With no voices nothing is set,
 * so the engine's own default voice is used. Choices already made are kept.
 */
export function defaultCasting(characters: Castable[], voices: Voice[], current: Casting = {}): Casting {
  const out: Casting = { ...current };
  if (voices.length === 0) return out;
  let general = 0;
  const perGender = new Map<string, number>();
  for (const character of characters) {
    if (castingValue(out, character)) continue;
    const gender = character.gender?.trim().toLowerCase();
    const sameGender = gender ? voices.filter((v) => v.gender?.trim().toLowerCase() === gender) : [];
    let pick: Voice;
    if (gender && sameGender.length > 0) {
      const n = perGender.get(gender) ?? 0;
      perGender.set(gender, n + 1);
      pick = sameGender[n % sameGender.length];
    } else {
      pick = voices[general % voices.length];
      general++;
    }
    for (const key of castKeys(character)) out[key] = pick.id;
  }
  return out;
}

/** An empty voice means Automatic: the keys are removed so the engine's default applies. */
export function setCharacterVoice(casting: Casting, character: Castable, voiceId: string): Casting {
  const out = { ...casting };
  for (const key of castKeys(character)) {
    if (voiceId) out[key] = voiceId; else delete out[key];
  }
  return out;
}

export function setNarratorVoice(casting: Casting, voiceId: string): Casting {
  const out = { ...casting };
  for (const key of NARRATOR_KEYS) {
    if (voiceId) out[key] = voiceId; else delete out[key];
  }
  return out;
}
