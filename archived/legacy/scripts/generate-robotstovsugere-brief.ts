import { writeFileSync } from "fs";
import { generateBrief } from "../src/services/brief-generator.js";
import { v4 as uuidv4 } from "uuid";

const category = "robotstovsugere";
const siteKey = "techblog";

const brief = generateBrief(category, undefined, siteKey);
const output = {
  job_id: uuidv4(),
  brief
};

writeFileSync(`prompts/brief-${category}-sample.json`, JSON.stringify(output, null, 2), "utf-8");
console.log(`✅ Generated prompts/brief-${category}-sample.json`);
