const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const OpenAI = require('openai');
const fs = require('fs');
const path = require('path');
const { createObjectCsvWriter } = require('csv-writer');

// --- CONFIGURATION ---
const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors()); // Allow widgets from any domain to connect
app.use(bodyParser.json());

// Secrets (Set these in Render/Replit Environment Variables)
const OPENAI_API_KEY = process.env.OPENAI_API_KEY; 
const ASSISTANT_ID = 'asst_6AnFZkW7f6Jhns774D9GNWXr'; // Your Nesta Agent

if (!OPENAI_API_KEY) {
  console.error("CRITICAL ERROR: OPENAI_API_KEY is missing from environment variables.");
  process.exit(1);
}

const openai = new OpenAI({ apiKey: OPENAI_API_KEY });
const CSV_FILE = path.join(__dirname, 'nesta_signals_log.csv');

// --- HELPER: CSV LOGGER ---
async function logSignalToCsv(data) {
  const csvWriter = createObjectCsvWriter({
    path: CSV_FILE,
    header: [
      { id: 'timestamp', title: 'TIMESTAMP' },
      { id: 'title', title: 'TITLE' },
      { id: 'score', title: 'SCORE' },
      { id: 'mission', title: 'MISSION' },
      { id: 'archetype', title: 'ARCHETYPE' },
      { id: 'hook', title: 'HOOK' },
      { id: 'sourceURL', title: 'SOURCE' }
    ],
    append: fs.existsSync(CSV_FILE) // Append if file exists
  });

  const record = {
    timestamp: new Date().toISOString(),
    title: data.title || "Unknown",
    score: data.score || 0,
    mission: data.mission || "Adj",
    archetype: data.archetype || "Signal",
    hook: data.hook || "",
    sourceURL: data.sourceURL || ""
  };

  await csvWriter.writeRecords([record]);
  console.log(`✅ Logged signal: ${record.title}`);
}

// --- HELPER: WIDGET JSON BUILDER ---
function buildWidgetPayload(data) {
  // Logic for badge color
  const score = data.score || 0;
  const scoreColor = score > 80 ? "success" : (score > 60 ? "warning" : "secondary");
  
  // Clean up data for display
  const archetype = (data.archetype || "SIGNAL").toUpperCase();
  const lenses = data.lenses || "Tech, Social";

  // The ChatKit Visual Card Structure
  return {
    "type": "Card",
    "size": "lg",
    "children": [
      {
        "type": "Col", "gap": 2,
        "children": [
          {
            "type": "Row", "gap": 2, "align": "center",
            "children": [
              { "type": "Icon", "name": "sparkle", "color": "primary" },
              { "type": "Title", "value": "Nesta Signal Scout", "size": "sm" },
              { "type": "Spacer" },
              { "type": "Badge", "label": "Pro", "color": "discovery" }
            ]
          },
          { "type": "Text", "value": "Identify, rank, and stress-test innovation signals.", "size": "sm", "color": "secondary" }
        ]
      },
      { "type": "Divider" },
      {
        "type": "Col", "gap": 2,
        "children": [
          { "type": "Divider", "flush": true },
          {
            "type": "Row", "align": "center",
            "children": [
              { "type": "Caption", "value": archetype, "size": "sm", "color": "tertiary" },
              { "type": "Spacer" },
              { "type": "Badge", "label": `Score: ${score}/100`, "color": scoreColor }
            ]
          },
          { "type": "Title", "value": data.title, "size": "md" },
          { "type": "Text", "value": data.hook, "size": "md" },
          {
            "type": "Row", "gap": 1,
            "children": [
              { "type": "Icon", "name": "tag", "size": "xs", "color": "tertiary" },
              { "type": "Caption", "value": lenses, "size": "sm", "color": "secondary" }
            ]
          },
          {
            "type": "Row", "gap": 2, "align": "center",
            "children": [
              { "type": "Badge", "label": data.mission, "color": "info" },
              { "type": "Spacer" },
              { 
                "type": "Button", 
                "label": "Use in chat", 
                "iconStart": "write", 
                "size": "sm",
                "onClickAction": { "type": "message.insert", "payload": { "text": `${data.title}: ${data.hook}` } } 
              },
              { 
                "type": "Button", 
                "label": "Source", 
                "variant": "outline", 
                "size": "sm", 
                "iconStart": "external-link",
                "onClickAction": { "type": "open.url", "payload": { "url": data.sourceURL } } 
              }
            ]
          }
        ]
      }
    ]
  };
}

// --- ROUTE 1: CHAT ENDPOINT ---
app.post('/api/chat', async (req, res) => {
  try {
    // 1. Parse Input
    // ChatKit might send { messages: [] } or { text: "" }
    let userMessage = "Find top signals";
    if (req.body.messages && req.body.messages.length > 0) {
      userMessage = req.body.messages[req.body.messages.length - 1].content;
    } else if (req.body.text) {
      userMessage = req.body.text;
    }

    console.log(`User asked: "${userMessage}"`);

    // 2. Create Thread & Run
    const run = await openai.beta.threads.createAndRun({
      assistant_id: ASSISTANT_ID,
      thread: {
        messages: [{ role: "user", content: userMessage }]
      }
    });

    // 3. Poll for Completion
    // We use a simple while loop with delay
    let runStatus = await openai.beta.threads.runs.retrieve(run.thread_id, run.id);

    while (runStatus.status !== 'completed') {
      // Check for failure
      if (runStatus.status === 'failed' || runStatus.status === 'cancelled' || runStatus.status === 'expired') {
        throw new Error(`Run failed with status: ${runStatus.status}`);
      }

      // Check for Action (The Widget Trigger)
      if (runStatus.status === 'requires_action') {
        const toolCalls = runStatus.required_action.submit_tool_outputs.tool_calls;
        
        // Find our specific visualization tool
        const displayAction = toolCalls.find(tc => tc.function.name === 'display_signal_card');

        if (displayAction) {
          console.log("Agent triggered Visual Card...");
          const rawArgs = displayAction.function.arguments;
          const signalData = JSON.parse(rawArgs);

          // A. Save to CSV
          await logSignalToCsv(signalData);

          // B. Send Visual Payload to Widget
          // Note: We do NOT submit tool outputs back to OpenAI here because we want to 
          // end the turn and show the card immediately. 
          // If you wanted the agent to continue talking, you would submit outputs here.
          return res.json(buildWidgetPayload(signalData));
        }
      }

      // Wait 1 second before polling again
      await new Promise(resolve => setTimeout(resolve, 1000));
      runStatus = await openai.beta.threads.runs.retrieve(run.thread_id, run.id);
    }

    // 4. Handle Text Completion (Fallback)
    // If the loop finishes without triggering the widget, return the text.
    const messages = await openai.beta.threads.messages.list(run.thread_id);
    const lastMsg = messages.data[0].content[0].text.value;

    return res.json({
      role: "assistant",
      content: lastMsg
    });

  } catch (error) {
    console.error("Error:", error);
    res.status(500).json({ error: error.message });
  }
});

// --- ROUTE 2: DOWNLOAD CSV ---
app.get('/api/download_csv', (req, res) => {
  if (fs.existsSync(CSV_FILE)) {
    res.download(CSV_FILE);
  } else {
    res.status(404).send("No signals have been logged yet.");
  }
});

// --- START SERVER ---
app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});
