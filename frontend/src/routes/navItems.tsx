import {
  BarChart3,
  Building2,
  FileText,
  LayoutDashboard,
  Mail,
  Radio,
  Settings,
  Sparkles,
  Target,
  Users,
} from 'lucide-react';
import type { ComponentType } from 'react';

export interface NavItem {
  label: string;
  to: string;
  icon: ComponentType<{ className?: string }>;
}

export const navItems: NavItem[] = [
  { label: 'Dashboard', to: '/dashboard', icon: LayoutDashboard },
  { label: 'Leads', to: '/leads', icon: Target },
  { label: 'Companies', to: '/companies', icon: Building2 },
  { label: 'Opportunities', to: '/opportunities', icon: Sparkles },
  { label: 'Signals', to: '/signals', icon: Radio },
  { label: 'Tenders', to: '/tenders', icon: FileText },
  { label: 'Contacts', to: '/contacts', icon: Users },
  { label: 'Outreach', to: '/outreach', icon: Mail },
  { label: 'Analytics', to: '/analytics', icon: BarChart3 },
  { label: 'Settings', to: '/settings', icon: Settings },
];
