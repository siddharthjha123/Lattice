"""Direct Orchestrator adapter; never substitutes competing scheduling logic."""

from orchestrator import service


class OrchestratorClient:
    validate_box_creation = staticmethod(service.validate_box_creation)
    create_box_placement = staticmethod(service.create_box_placement)
    select_deployment_worker = staticmethod(service.select_deployment_worker)
    select_failover_worker = staticmethod(service.select_failover_worker)
    release_box_reservation = staticmethod(service.release_box_reservation)
    calculate_worker_capacity = staticmethod(service.calculate_worker_capacity)


orchestrator_client = OrchestratorClient()
