import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import ApprovalPanel from "../components/ApprovalPanel";

const payload = {
  kind: "action" as const,
  action: { tool: "issue_refund", args: { amount_cents: 5900 } },
  reasons: ["write actions require human approval",
            "refund $59.00 exceeds the $50.00 auto-approval threshold"],
  policy_ref: "Refunds & Duplicate Charges",
};

describe("ApprovalPanel", () => {
  it("renders the pending action and approves", () => {
    const onDecision = vi.fn();
    render(<ApprovalPanel payload={payload} busy={false} onDecision={onDecision} />);
    expect(screen.getByTestId("approval-tool")).toHaveTextContent("issue_refund");
    expect(screen.getByText(/threshold/i)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("approve-btn"));
    expect(onDecision).toHaveBeenCalledWith(true, "");
  });
});