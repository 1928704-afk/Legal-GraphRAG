import legalData from '../data/legal_bundle.json';

export async function onRequestGet({ env }) {
  return new Response(JSON.stringify({
    status: "ok",
    platform: "Cloudflare Pages & Workers AI",
    total_laws_indexed: legalData.total_docs,
    total_kg_triples: legalData.triples.length,
    workers_ai_available: !!(env && env.AI)
  }), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store"
    }
  });
}
