// Keep provider selection in the native model node; fail before unverified use.
const model = await this.getInputConnectionData("ai_languageModel", 0);
const provider = model?._llmType?.();
if (!["googlegenerativeai", "openai", "anthropic"].includes(provider)) {
  throw new Error("此模型的重试控制尚未验证，月报已停止；不会调用模型。");
}
function disableRetries(instance) {
  if (!instance?.caller || typeof instance.caller.maxRetries !== "number") {
    throw new Error("模型重试接口已变化，月报已停止；不会调用模型。");
  }
  instance.caller.maxRetries = 0;
  instance.maxRetries = 0;
  instance.streaming = false;
  const tokenField =
    provider === "googlegenerativeai" ? "maxOutputTokens" : "maxTokens";
  instance[tokenField] = Math.min(instance[tokenField] ?? 8192, 8192);
  if (instance.clientConfig) instance.clientConfig.maxRetries = 0;
  if (instance.clientOptions) instance.clientOptions.maxRetries = 0;
  for (const key of ["client", "batchClient", "streamingClient"]) {
    if (instance[key] && "maxRetries" in instance[key])
      instance[key].maxRetries = 0;
  }
}
disableRetries(model);
if (provider === "openai") {
  // Current ChatOpenAI delegates to distinct completions/responses instances.
  for (const key of ["completions", "responses"]) {
    if (model[key]) disableRetries(model[key]);
  }
}
return model;
