Feature: NEXUS trust-layer acceptance invariants
  Executable acceptance specs for the moat invariants (000-docs/009 #20).
  These are the L6/L7 layer the audit flagged as absent (0 .feature files) —
  the human-readable contract that the policy gate + pipeline must uphold.

  Scenario: LOCAL mode makes zero external calls, fail-closed (invariant 2)
    Given the policy engine is in "local" mode
    When a cloud LLM call is guarded
    Then the call is blocked

  Scenario: A secret is blocked before any cloud call (invariant 6)
    Given the policy engine is in "hybrid" mode
    When a payload containing an AWS access key is guarded for a cloud LLM
    Then the call is blocked
    And the "aws_access_key" secret pattern is reported

  Scenario: Insufficient evidence forces a refusal, not a guess (invariant 3)
    Given a pipeline whose top retrieval score is 0.1
    And an evidence floor of 0.5
    When the knowledge base is queried
    Then the answer is the insufficient-evidence refusal
    And no citations are returned
    And the language model is never called
