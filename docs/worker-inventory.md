# Worker and pool inventory

Workers retain stable identities, enrollment scope, current capacity and lifecycle state. Retired entries use soft deletion so historical deployments remain interpretable. Offline is not deleted, and registration alone is not proof of usable capacity.

Worker deletion requires management authorization and is blocked by live channels, workloads, reservations, active Box references or an unexpired fencing window. Drain and disconnect safely first. A retired identity cannot silently rejoin; enroll a new identity using a new state directory.

Pool deletion requires removal of its workers and Boxes. Enrollment is revoked and history retained; names remain reserved. These operations are exposed by the authenticated dashboard and management API. Never delete database rows manually to skip lifecycle checks.
