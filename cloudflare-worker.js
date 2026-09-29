// MJR Morning Brief Newsletter Publisher
// Cloudflare Worker
//
// Required Worker secrets/variables:
//   GITHUB_TOKEN  - fine-grained GitHub token with Actions: Read and write
//   PUBLISH_KEY   - optional shared key if you later want an additional gate
//
// After deployment, set the Manager endpoint once in the browser console:
// localStorage.setItem("mjrNewsletterPublishEndpoint","https://YOUR-WORKER.workers.dev/");

const OWNER = "Mediajobsreport";
const REPO = "mjr-morning-brief-feed";
const WORKFLOW = "manage-newsletter.yml";
const ALLOWED_ORIGIN = "https://mediajobsreport.github.io";

function cors(origin) {
  return {
    "Access-Control-Allow-Origin": origin === ALLOWED_ORIGIN ? origin : ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store"
  };
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors(origin) });
    }
    if (request.method !== "POST") {
      return new Response(JSON.stringify({ok:false,error:"Method not allowed"}), {status:405,headers:cors(origin)});
    }
    if (origin !== ALLOWED_ORIGIN) {
      return new Response(JSON.stringify({ok:false,error:"Origin not allowed"}), {status:403,headers:cors(origin)});
    }
    if (!env.GITHUB_TOKEN) {
      return new Response(JSON.stringify({ok:false,error:"Publisher is not configured."}), {status:500,headers:cors(origin)});
    }

    let body;
    try { body = await request.json(); }
    catch { return new Response(JSON.stringify({ok:false,error:"Invalid request."}), {status:400,headers:cors(origin)}); }

    const action = body.action === "refresh" ? "refresh" : "publish_manager";
    const payload = String(body.payload || "");
    if (action === "publish_manager" && (!payload || payload.length > 30000 || !/^[A-Za-z0-9+/=]+$/.test(payload))) {
      return new Response(JSON.stringify({ok:false,error:"Invalid publish data."}), {status:400,headers:cors(origin)});
    }

    const url = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;
    const gh = await fetch(url, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "MJR-Newsletter-Publisher"
      },
      body: JSON.stringify({
        ref: "main",
        inputs: { action, payload: action === "publish_manager" ? payload : "", item: "" }
      })
    });

    if (!gh.ok) {
      const detail = (await gh.text()).slice(0,500);
      return new Response(JSON.stringify({ok:false,error:"GitHub publisher rejected the request.",detail}), {status:502,headers:cors(origin)});
    }
    return new Response(JSON.stringify({ok:true,message: action === "refresh" ? "Story refresh started." : "Morning Brief publish started."}), {status:200,headers:cors(origin)});
  }
};
