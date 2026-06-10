"""Atlas integration adapters for Project Intelligence (PI-17+).

Adapters live OUTSIDE the portable module cores (ADR-PI-014): they may bridge Atlas planner/
generator/verification call sites to the Project Intelligence facade. They never expose a
module-private store to the consumer.
"""
