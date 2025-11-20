import requests
from fastapi import HTTPException, status
from repository.iparking_repository import IParkingRepository
from schemas.parking import ParkingSnapshotCreate, ParkingSnapshotResponse


class ParkingService:
    def __init__(self, parking_repo: IParkingRepository, base_url: str = "http://10.41.11.21:9696"):
        self.parking_repo = parking_repo
        self.edge_base_url = base_url

    def get_latest_snapshot(self) -> ParkingSnapshotResponse:
        snapshot = self.parking_repo.get_latest_snapshot()
        if not snapshot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No parking snapshot found",
            )
        return ParkingSnapshotResponse.from_orm(snapshot)

    def get_latest_snapshot2(self) -> ParkingSnapshotResponse:
        snapshot = self.parking_repo.get_latest_snapshot2()
        if not snapshot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No parking snapshot found",
            )
        return ParkingSnapshotResponse.from_orm(snapshot)

    def create_snapshot(self, snapshot_data: ParkingSnapshotCreate) -> ParkingSnapshotResponse:
        snapshot = self.parking_repo.create_snapshot(snapshot_data)
        return ParkingSnapshotResponse.from_orm(snapshot)
    
    def infer_parking1_snapshot(self) -> bytes:
        """
        Calls the inference server and returns the visualization image bytes.
        """
        url = f"{self.edge_base_url}/infer/parking1"
        response = requests.get(url)
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Inference server error: {response.status_code}",
            )
        return response.content  # raw image bytes
    
    def infer_parking2_snapshot(self) -> bytes:
        """
        Calls the inference server and returns the visualization image bytes.
        """
        url = f"{self.edge_base_url}/infer/parking2"
        response = requests.get(url)
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Inference server error: {response.status_code}",
            )
        return response.content  # raw image bytes
    
    def open_gate(self) -> dict:
        """
        Calls the edge server's /open endpoint to trigger the relay.
        """
        url = f"{self.edge_base_url}/open"
        try:
            response = requests.get(url, timeout=5)
        except requests.RequestException as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Edge server unreachable: {e}",
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Edge server error: {response.status_code}",
            )

        return response.json()

    def get_exit_gate_status(self) -> dict:
        """
        Gets the status of the exit gate service from the edge server.
        """
        url = f"{self.edge_base_url}/exit-gate/status"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Edge server unreachable: {e}",
            )

    def start_exit_gate_service(self) -> dict:
        """
        Starts the exit gate service on the edge server.
        """
        url = f"{self.edge_base_url}/exit-gate/start"
        try:
            response = requests.post(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Edge server unreachable: {e}",
            )

    def stop_exit_gate_service(self) -> dict:
        """
        Stops the exit gate service on the edge server.
        """
        url = f"{self.edge_base_url}/exit-gate/stop"
        try:
            response = requests.post(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Edge server unreachable: {e}",
            )
