// Deliver the profile as soon as it arrives, regardless of model latency/failure.
export async function loadEmployeeResources({ employeeId, request, onProfile, onRecommendations, onProfileError, onRecommendationError }) {
  const id = encodeURIComponent(employeeId);
  await Promise.all([
    request(`/employees/${id}`).then(onProfile).catch(onProfileError),
    request(`/recommend/${id}`).then(onRecommendations).catch(onRecommendationError),
  ]);
}
