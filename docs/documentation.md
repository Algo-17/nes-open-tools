# Documentation

> This document was written by jdharms

## Agentic Development

Most of the work in this repository happens via Claude Code/Codex sessions.  One
of the aspects of working with AI agents that I'm still getting used to is the
extreme "statelessness" of it.  Anything that is not written down somewhere will
have to be re-derived by the agent on every relevant session down the line.  There's
a real tension between over-documenting and under-documenting for a lot of this.
Having too much documentation leads to agents becoming confused between what
*exists* and what is *desired*, generally degraded performance via too much
brought into context, and higher likelihood of drift between what the code
does and what the documentation says.  Under-documenting means that, as stated
above, agents need to "figure out" more things in more sessions.  The risks
here are that the process is error-prone (they might look in the wrong place
and assume something doesn't exist), it is expensive in terms of tokens and
context, and it encourages "guessing" by the agent.  Finally, it's a drag
on developer time having to re-explain things in-session.

## Documentation Types

Development-related documentation should primarily do the following, in my
opinion:

* Record what is in-scope/not in-scope
* Define the terms used across the application, including both the nouns (domain entities)
and verbs (operations on one or more domain entities).  In the same place it's useful to
define the invariants, pre-conditions, post-conditions, etc of all terms.
* Record any decisions that are made, so that they don't have to be re-litigated again.
A recorded decision doesn't have to be permanent, but if not it should have a fairly
well-defined description of what would cause it to need to be rethought.

Three different forms of documentation perform these three roles.

### Product Requirements Document

Currently this does not exist in the repository, though `docs/randomizer.md` and
`docs/randomizer_devplan.md` are currently *close* to this for the randomizer.  In
general this should be a document that explains what is and isn't in scope
from a features/capabilities perspective, while trying to remain technology/architecture
agnostic as much as possible.  If a feature in the PRD isn't implemented yet, that
is 'future work'.  If the implementation conflicts with the PRD, that is a bug--either
in the PRD or in the code.

### Glossary

The glossary defines the terms used across the application.  The glossary can
include the semantics of the various operations that can be performed on
the domain entities, but should attempt to keep architectural *details*
left out.  For example, the glossary might say that when a new `foo` is
added to the system with the same `bar` as an existing one, that it should
replace it.  The glossary shouldn't really care if a row in a database is
actually deleted, or marked as `hidden`, or any other method to achieve this goal.

(Also currently not implemented in this repo.)

### Architecture Decision Records

This one is a little "looser" than how some others define it.  I think that
it's more important for these to capture the *decisions* than it is for
them to capture the *architecture*.  Generally any time something is
decided around architecture, technologies/tooling, or even a
product decision that might need to be revisited, an ADR should be made
that lists alternatives considered, consequences, and a reason to
revisit the decision.

## Rejected Documentation

I think that any implementation-level documentation or spec is probably
not worth keeping around in a mostly agentic workflow.  In software teams,
a "Technical Design Doc" is often used to plan out architecture or
software design decisions.  The main thing these documents do is
put the details into words that can be communicated with team members,
reviewed, and then if needed handed off to someone else for development.
At this point even for traditional software teams the value of the documents
falls off.  If someone thinks the system has a bug, then reviewing the TDD
can only possibly tell you if the bug is that something wasn't accounted
for in the technical design, but it definitely can't tell you if the bug
exists or if the behavior was ever asked for (i.e., specified).

I think that the TDD is mostly replaced by the in-session conversation
with the agent, and is also generally not worth persisting beyond that.
To find out what the code does... read the code.