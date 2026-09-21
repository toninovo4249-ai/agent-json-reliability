// Local HTTP example. Set PUBLIC_BASE_URL for a remote origin.
const BASE = process.env.PUBLIC_BASE_URL || "http://127.0.0.1:8770";

const positive = {
  text: "```json\n{\"name\":\"alice\",\"age\":30,}\n```",
  schema: { type: "object", required: ["name", "age"] },
};
const refusal = { text: '{"user":' };

async function reliable(body) {
  const r = await fetch(BASE.replace(/\/$/, "") + "/v1/json/reliable", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

const pos = await reliable(positive);
const ref = await reliable(refusal);
console.log("positive", pos.valid_final, pos.json);
console.log("refusal", ref.valid_final, ref.unsafe_or_ambiguous, ref.repaired);
