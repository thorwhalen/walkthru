import { describe, it, expect } from "vitest";
import { hello } from "./index.js";

describe("hello", () => {
  it("greets the world by default", () => {
    expect(hello()).toBe("Hello, world!");
  });

  it("greets a given name", () => {
    expect(hello("wads")).toBe("Hello, wads!");
  });
});
