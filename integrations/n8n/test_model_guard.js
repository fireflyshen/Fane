// Uses the installed n8n SDKs with fake credentials and an in-memory transport.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(path.join(__dirname, "model_guard.js"), "utf8");
const guard = new AsyncFunction(source);
const prepare = (model) =>
    guard.call({ getInputConnectionData: async () => model });

async function main() {
    let requests = 0;
    let successPayload = null;
    // No real network access: every SDK request is replaced with this function.
    globalThis.fetch = async () => {
        requests++;
        return new Response(
            JSON.stringify(
                successPayload ?? {
                    error: {
                        code: 503,
                        status: "UNAVAILABLE",
                        type: "api_error",
                        message: "Fixture failure",
                    },
                    type: "error",
                },
            ),
            {
                status: successPayload ? 200 : 503,
                headers: { "content-type": "application/json" },
            },
        );
    };
    const req = createRequire(
        path.join(process.env.N8N_LANGCHAIN_PACKAGE, "package.json"),
    );
    const { JavaScriptSandbox } = req(
        "n8n-nodes-base/dist/nodes/Code/JavaScriptSandbox",
    );
    const { vmResolver } = req(
        path.join(
            process.env.N8N_LANGCHAIN_PACKAGE,
            "dist/nodes/code/Code.node.js",
        ),
    );
    const { ChatGoogleGenerativeAI } = req("@langchain/google-genai");
    const { ChatOpenAI } = req("@langchain/openai");
    const { ChatAnthropic } = req("@langchain/anthropic");
    const { ChainLlm } = req(
        path.join(
            process.env.N8N_LANGCHAIN_PACKAGE,
            "dist/nodes/chains/ChainLLM/ChainLlm.node.js",
        ),
    );
    const fixtures = {
        Gemini: {
            candidates: [
                {
                    content: {
                        role: "model",
                        parts: [{ text: '{"fixture":true}' }],
                    },
                    finishReason: "STOP",
                },
            ],
        },
        "OpenAI completions": {
            id: "fixture",
            choices: [
                {
                    index: 0,
                    message: { role: "assistant", content: '{"fixture":true}' },
                    finish_reason: "stop",
                },
            ],
        },
        "OpenAI responses": {
            id: "resp_fixture",
            object: "response",
            status: "completed",
            model: "fixture",
            output: [
                {
                    id: "msg_fixture",
                    type: "message",
                    role: "assistant",
                    status: "completed",
                    content: [
                        {
                            type: "output_text",
                            text: '{"fixture":true}',
                            annotations: [],
                        },
                    ],
                },
            ],
        },
        Anthropic: {
            id: "msg_fixture",
            type: "message",
            role: "assistant",
            model: "fixture",
            content: [{ type: "text", text: '{"fixture":true}' }],
            stop_reason: "end_turn",
            stop_sequence: null,
            usage: { input_tokens: 1, output_tokens: 1 },
        },
    };
    for (const [name, factory] of [
        [
            "Gemini",
            () =>
                new ChatGoogleGenerativeAI({
                    apiKey: "fixture",
                    model: "gemini-fixture",
                }),
        ],
        [
            "OpenAI completions",
            () =>
                new ChatOpenAI({
                    apiKey: "fixture",
                    model: "fixture",
                    useResponsesApi: false,
                }),
        ],
        [
            "OpenAI responses",
            () =>
                new ChatOpenAI({
                    apiKey: "fixture",
                    model: "fixture",
                    useResponsesApi: true,
                }),
        ],
        [
            "Anthropic",
            () => new ChatAnthropic({ apiKey: "fixture", model: "fixture" }),
        ],
    ]) {
        requests = 0;
        successPayload = null;
        const original = factory();
        const sandbox = new JavaScriptSandbox(
            { getInputConnectionData: async () => original },
            source,
            {},
            { resolver: vmResolver },
        );
        const model = await sandbox.runCode();
        await assert.rejects(
            model.invoke("Synthetic fixture; no financial data"),
        );
        assert.equal(requests, 1, name + " must not retry a 503 response");
        console.log(
            "PASS " +
                name +
                ": n8n sandbox + 503 results in exactly one mocked request",
        );
        requests = 0;
        successPayload = fixtures[name];
        const successfulModel = await new JavaScriptSandbox(
            { getInputConnectionData: async () => factory() },
            source,
            {},
            { resolver: vmResolver },
        ).runCode();
        const values = {
            hasOutputParser: false,
            needsFallback: false,
            promptType: "define",
            text: "Synthetic fixture",
            "batching.batchSize": 1,
        };
        const context = {
            logger: { debug() {} },
            getInputData: () => [{ json: { fixture: true } }],
            getNode: () => ({ name: "Fixture chain", typeVersion: 1.9 }),
            getNodeParameter: (name, _index, fallback) =>
                values[name] ?? fallback,
            getInputConnectionData: async (type) =>
                type === "ai_languageModel" ? successfulModel : null,
            getWorkflow: () => ({ id: "fixture", name: "Fixture workflow" }),
            getExecutionId: () => "fixture",
            getExecutionCancelSignal: () => new AbortController().signal,
            continueOnFail: () => false,
        };
        const output = await new ChainLlm().execute.call(context);
        assert.equal(requests, 1, name + " success must use one request");
        assert.equal(output[0][0].json.text, '{"fixture":true}');
        console.log(
            "PASS " +
                name +
                ": Basic LLM Chain produces report text with one mocked request",
        );
    }
    await assert.rejects(
        prepare({ _llmType: () => "unknown", caller: { maxRetries: 6 } }),
    );
    await assert.rejects(prepare({ _llmType: () => "googlegenerativeai" }));
    console.log("PASS unknown provider or changed SDK: stops before a request");
}
main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
