import { generateBriefAsync } from "../src/services/brief-generator.js";
process.env["PR_HUS_PARTNER_ID"] = "adrunner_dk_husforbegyndere";
const result = await generateBriefAsync({ category: "kaffemaskiner", site: "husforbegyndere" });
console.log(JSON.stringify(result, null, 2));
