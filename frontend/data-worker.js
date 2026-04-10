/* data-worker.js */

self.onmessage = function(e) {
    const { action, filters } = e.data;

    if (action === 'filter') {
        const { 
            allMarkersData, 
            selectedStatuses, 
            selectedStations,
            selectedBuckets, 
            initiativesFilter, 
            jurisdictionFilter
        } = filters;
        
        const statusAllSelected = selectedStatuses.includes('all');
        const stationAllSelected = selectedStations.includes('all');
        const bucketsAllSelected = selectedBuckets.includes('all');

        // Processamento pesado de filtragem em thread separada
        const filtered = allMarkersData.filter(marker => {
            const statusMatch = statusAllSelected || selectedStatuses.includes(marker.status);
            const stationMatch = stationAllSelected || selectedStations.includes(marker.delivery_station);
            const bucketMatch = bucketsAllSelected || selectedBuckets.includes(marker.bucket_ade)
            
            let initiativesMatch = true;
            if (initiativesFilter !== 'all') {
                if (initiativesFilter === 'null') {
                    initiativesMatch = (
                        marker.hub_delivey_initiatives === null ||
                        marker.hub_delivey_initiatives === undefined ||
                        marker.hub_delivey_initiatives === '' ||
                        marker.hub_delivey_initiatives === 'N/A'
                    );
                } else {
                    initiativesMatch = marker.hub_delivey_initiatives === initiativesFilter;
                }
            }

            const jurisdictionMatch = jurisdictionFilter === 'all' || marker.jurisdiction_type === jurisdictionFilter;

            return statusMatch && stationMatch && initiativesMatch && jurisdictionMatch && bucketMatch;
        });

        // Retorna o resultado para a Main Thread
        self.postMessage({ action: 'filterResult', filtered });
    }
};
