import { readFileSync } from "node:fs";

const mode = process.argv[2];
const input = JSON.parse(readFileSync(0, "utf8"));
if (!Array.isArray(input) || input.length > 16) throw new Error("Invalid batch");
const MAX_SVG = 256 * 1024;
const MAX_PNG = 1024 * 1024;

async function svgBatch() {
  globalThis.MathJax = {
    loader: {
      paths: { mathjax: "@mathjax/src/bundle" },
      load: ["input/tex-base", "[tex]/ams", "[tex]/boldsymbol", "output/svg", "adaptors/liteDOM"],
      require: file => import(file)
    },
    tex: {
      packages: ["base", "ams", "boldsymbol"],
      maxBuffer: 4096,
      maxMacros: 1000,
      tags: "none",
      formatError: (_jax, error) => { throw error; }
    },
    output: { font: "mathjax-newcm" },
    svg: { fontCache: "none" }
  };
  await import("@mathjax/src/bundle/startup.js");
  const mj = globalThis.MathJax;
  await mj.startup.promise;
  const adaptor = mj.startup.adaptor;
  try {
    for (const item of input) {
      try {
        mj.texReset();
        const node = await mj.tex2svgPromise(item.value, {
          display: true, em: 16, ex: 8, containerWidth: 1280
        });
        const svg = adaptor.tags(node, "svg")[0];
        if (!svg) throw new Error("No SVG");
        if (adaptor.tags(svg, "g").some(g => adaptor.getAttribute(g, "data-mml-node") === "merror"))
          throw new Error("TeX error node");
        const value = adaptor.serializeXML(svg);
        if (Buffer.byteLength(value) > MAX_SVG) throw new Error("SVG size limit");
        console.log(JSON.stringify({id: item.id, value}));
      } catch (error) {
        console.log(JSON.stringify({id: item.id, error: String(error.message || error).slice(0, 200)}));
      }
    }
  } finally {
    mj.done();
  }
}

async function pngBatch() {
  const { Resvg } = await import("@resvg/resvg-js");
  for (const item of input) {
    try {
      const png = new Resvg(item.value, {font: {loadSystemFonts: false}}).render().asPng();
      if (png.length > MAX_PNG) throw new Error("PNG size limit");
      console.log(JSON.stringify({id: item.id, value: Buffer.from(png).toString("base64")}));
    } catch (error) {
      console.log(JSON.stringify({id: item.id, error: String(error.message || error).slice(0, 200)}));
    }
  }
}

if (mode === "svg") await svgBatch();
else if (mode === "png") await pngBatch();
else throw new Error("Invalid rendering mode");
