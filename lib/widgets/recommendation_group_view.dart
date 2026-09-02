import 'package:flutter/material.dart';
import 'package:trip_logic/models/recommendation_group.dart';
import 'package:trip_logic/models/travel_context.dart';

class RecommendationGroupView extends StatelessWidget {
  const RecommendationGroupView({super.key, required this.group});

  final RecommendationGroup group;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final recommendations = group.result.allRecommendations;

    return Container(
      margin: const EdgeInsets.only(top: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(
                _groupIcon(group.recommendationType),
                size: 20,
                color: theme.colorScheme.primary,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  _groupTitle(group.recommendationType),
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              if (group.result.count > 0)
                Text(
                  '${group.result.count}',
                  style: theme.textTheme.labelLarge?.copyWith(
                    color: theme.colorScheme.primary,
                    fontWeight: FontWeight.w700,
                  ),
                ),
            ],
          ),
          if (group.travellerQuery != null) ...[
            const SizedBox(height: 4),
            Text(
              group.travellerQuery!,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
          const SizedBox(height: 10),
          if (recommendations.isEmpty)
            Text(
              group.result.message ?? 'No matching recommendations were found.',
              style: theme.textTheme.bodyMedium,
            )
          else
            for (final recommendation in recommendations) ...[
              _PlaceRecommendationCard(recommendation: recommendation),
              if (recommendation != recommendations.last)
                const SizedBox(height: 10),
            ],
        ],
      ),
    );
  }
}

class _PlaceRecommendationCard extends StatelessWidget {
  const _PlaceRecommendationCard({required this.recommendation});

  final PlaceRecommendation recommendation;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final route = recommendation.route;
    final weather = recommendation.weatherSuitability;

    final categoryNames = recommendation.categories
        .map((category) => category.name)
        .where((name) => name.trim().isNotEmpty)
        .toList();

    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (recommendation.rank != null)
                  Container(
                    width: 30,
                    height: 30,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary.withValues(alpha: 0.12),
                      shape: BoxShape.circle,
                    ),
                    child: Text(
                      '${recommendation.rank}',
                      style: theme.textTheme.labelLarge?.copyWith(
                        color: theme.colorScheme.primary,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                if (recommendation.rank != null) const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        recommendation.name,
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      if (recommendation.score != null) ...[
                        const SizedBox(height: 3),
                        Text(
                          'Match score: '
                          '${recommendation.score!.toStringAsFixed(1)}',
                          style: theme.textTheme.labelMedium?.copyWith(
                            color: theme.colorScheme.primary,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
            if (categoryNames.isNotEmpty) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final category in categoryNames)
                    Chip(
                      label: Text(category),
                      visualDensity: VisualDensity.compact,
                    ),
                ],
              ),
            ],
            if (recommendation.location?.displayAddress != null) ...[
              const SizedBox(height: 10),
              _InformationRow(
                icon: Icons.location_on_outlined,
                text: recommendation.location!.displayAddress!,
              ),
            ],
            const SizedBox(height: 8),
            _InformationRow(
              icon: Icons.star_outline,
              text: _ratingDescription(recommendation.rating),
            ),
            const SizedBox(height: 8),
            _InformationRow(
              icon: Icons.access_time_outlined,
              text: _hoursDescription(recommendation.hours),
            ),
            const SizedBox(height: 8),
            _InformationRow(
              icon: Icons.straighten_outlined,
              text: _distanceDescription(recommendation),
            ),
            if (route != null && route.available) ...[
              const SizedBox(height: 8),
              _InformationRow(
                icon: Icons.route_outlined,
                text: _routeDescription(route),
              ),
            ],
            if (route?.remainingVisitMinutes != null) ...[
              const SizedBox(height: 8),
              _InformationRow(
                icon: Icons.schedule_outlined,
                text:
                    '${route!.remainingVisitMinutes!.round()} '
                    'minutes remain for the visit',
              ),
            ],
            if (weather?.message != null) ...[
              const SizedBox(height: 8),
              _InformationRow(
                icon: _weatherIcon(weather!.status),
                text: weather.message!,
              ),
            ],
            if (recommendation.explanation != null) ...[
              const SizedBox(height: 12),
              Text(
                recommendation.explanation!,
                style: theme.textTheme.bodySmall?.copyWith(height: 1.45),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _InformationRow extends StatelessWidget {
  const _InformationRow({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 17, color: theme.colorScheme.onSurfaceVariant),
        const SizedBox(width: 7),
        Expanded(
          child: Text(
            text,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              height: 1.35,
            ),
          ),
        ),
      ],
    );
  }
}

String _groupTitle(TravelRequestKind kind) {
  switch (kind) {
    case TravelRequestKind.attraction:
      return 'Attraction recommendations';
    case TravelRequestKind.hotel:
      return 'Hotel recommendations';
    case TravelRequestKind.restaurant:
      return 'Restaurant recommendations';
    case TravelRequestKind.unknown:
      return 'Recommendations';
  }
}

IconData _groupIcon(TravelRequestKind kind) {
  switch (kind) {
    case TravelRequestKind.attraction:
      return Icons.attractions_outlined;
    case TravelRequestKind.hotel:
      return Icons.hotel_outlined;
    case TravelRequestKind.restaurant:
      return Icons.restaurant_outlined;
    case TravelRequestKind.unknown:
      return Icons.place_outlined;
  }
}

String _routeDescription(RecommendationRoute route) {
  final parts = <String>[];

  if (route.durationMinutes != null) {
    parts.add('${route.durationMinutes!.round()} minutes');
  }

  if (route.travelMode != null) {
    parts.add('by ${route.travelMode}');
  }

  if (parts.isEmpty) {
    return 'Route information available';
  }

  return parts.join(' · ');
}

String _ratingDescription(double? rating) {
  if (rating == null) {
    return 'Rating: Not available';
  }

  return 'Rating: ${rating.toStringAsFixed(1)}/10';
}

String _hoursDescription(RecommendationOpeningHours? hours) {
  if (hours == null) {
    return 'Hours: Not available';
  }

  final display = hours.display;

  if (display != null) {
    return 'Hours: $display';
  }

  if (hours.regular.isEmpty) {
    return 'Hours: Not available';
  }

  final intervalsByDay = <int, List<RecommendationOpeningInterval>>{};

  for (final interval in hours.regular) {
    intervalsByDay.putIfAbsent(interval.day, () => []).add(interval);
  }

  final daySchedules = <String>[];

  for (final day in intervalsByDay.keys.toList()..sort()) {
    final intervals = intervalsByDay[day]!;
    final schedule = intervals.map(_openingIntervalDescription).join(', ');
    daySchedules.add('${_weekdayName(day)} $schedule');
  }

  return 'Hours: ${daySchedules.join('; ')}';
}

String _openingIntervalDescription(RecommendationOpeningInterval interval) {
  if (interval.allDay == true) {
    return 'Open 24 hours';
  }

  final overnightLabel = interval.overnight == true ? ' (next day)' : '';

  return '${interval.openingTime}–${interval.closingTime}$overnightLabel';
}

String _weekdayName(int day) {
  return switch (day) {
    1 => 'Mon',
    2 => 'Tue',
    3 => 'Wed',
    4 => 'Thu',
    5 => 'Fri',
    6 => 'Sat',
    7 => 'Sun',
    _ => '',
  };
}

String _distanceDescription(PlaceRecommendation recommendation) {
  final routeDistance = recommendation.route?.distanceKilometres;

  if (recommendation.route?.available == true &&
      routeDistance != null &&
      routeDistance.isFinite &&
      routeDistance >= 0) {
    return 'Route distance: ${routeDistance.toStringAsFixed(1)} km';
  }

  final searchDistance = recommendation.distanceMeters;

  if (searchDistance == null || searchDistance < 0) {
    return 'Distance: Not available';
  }

  if (searchDistance < 1000) {
    return 'From search area: $searchDistance m';
  }

  return 'From search area: '
      '${(searchDistance / 1000).toStringAsFixed(1)} km';
}

IconData _weatherIcon(String? status) {
  switch (status) {
    case 'suitable':
      return Icons.check_circle_outline;
    case 'warning':
      return Icons.warning_amber_rounded;
    case 'unsuitable':
      return Icons.error_outline;
    default:
      return Icons.cloud_outlined;
  }
}
