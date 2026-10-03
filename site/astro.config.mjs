import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

// GitHub Pages 项目站点部署在 /ai-job-radar/ 子路径下；本地 dev/build 同样生效
export default defineConfig({
  site: "https://tech--man.github.io",
  base: "/ai-job-radar",
  vite: {
    plugins: [tailwindcss()],
  },
});
