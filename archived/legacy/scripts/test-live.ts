import axios from "axios";

async function test() {
  try {
    console.log("Testing POST /generate with live PriceRunner lookup...");
    const res = await axios.post("http://localhost:3000/generate", {
      category: "laptops",
      site: "techblog"
    });
    console.log("Success!");
    console.log(JSON.stringify(res.data, null, 2));
  } catch (err) {
    if (axios.isAxiosError(err)) {
      console.error("Error:", err.response?.status, err.response?.data);
    } else {
      console.error("Error:", err);
    }
  }
}

test();
