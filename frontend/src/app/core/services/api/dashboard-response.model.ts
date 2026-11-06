import { DailyActivity } from '../../models/activity.model';

export interface DashboardResponse {
  user_id: number;
  week: DailyActivity[];
}

