import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "成长小队 GrowthCrew",
    short_name: "成长小队",
    description: "贴入你的计划，AI 排进每天并盯着你执行",
    start_url: "/",
    display: "standalone",
    orientation: "portrait",
    theme_color: "#FDFCF8",
    background_color: "#FDFCF8",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
      },
    ],
  };
}
