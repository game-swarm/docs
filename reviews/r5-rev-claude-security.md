I've now read DESIGN.md in full, all nine P0 specs, and the R4 Speaker verdict. I have enough to write the R5 security review. Let me think through the attack surface from an adversary's seat before writing.

Key new findings worth flagging — the most serious is that the prompt-injection delimiter contract in P0-3 §6.3 is **forgeable** because the player-name charset includes every character the static
