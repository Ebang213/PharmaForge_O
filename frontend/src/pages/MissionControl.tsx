import { Link } from 'react-router-dom';
import { Upload, Shield, Radio, ClipboardList, ArrowRight, Clock } from 'lucide-react';
import HealthStatus from '../components/HealthStatus';

interface WorkflowStep {
    step: number;
    title: string;
    description: string;
    icon: React.ElementType;
    link: string;
    linkLabel: string;
}

const workflowSteps: WorkflowStep[] = [
    {
        step: 1,
        title: 'Upload Evidence',
        description: 'Upload regulatory documents, audit reports, and compliance evidence for analysis.',
        icon: Upload,
        link: '/watchtower',
        linkLabel: 'Go to Evidence Upload'
    },
    {
        step: 2,
        title: 'Identify Compliance Exposure',
        description: 'AI-powered analysis identifies regulatory gaps and compliance risks in your documentation.',
        icon: Shield,
        link: '/copilot',
        linkLabel: 'Open Compliance Copilot'
    },
    {
        step: 3,
        title: 'Correlate Supply Chain Risk',
        description: 'Monitor FDA feeds, shortages, and recalls. Map risks to your vendor network.',
        icon: Radio,
        link: '/watchtower',
        linkLabel: 'View Risk Radar'
    },
    {
        step: 4,
        title: 'Generate Action Plan',
        description: 'Collaborate with stakeholders to prioritize and assign remediation actions.',
        icon: ClipboardList,
        link: '/war-council',
        linkLabel: 'Open Decision Council'
    }
];

export default function MissionControl() {
    return (
        <div className="page-container">
            <div className="page-header">
                <div>
                    <h1>Risk Intelligence Loop</h1>
                    <p className="text-muted">
                        Your unified workflow for proactive pharmaceutical risk management
                    </p>
                </div>
            </div>

            {/* Start Here CTA */}
            <div className="start-here-banner">
                <div className="start-here-content">
                    <h2>Ready to begin?</h2>
                    <p>Run the complete Golden Workflow: Upload Evidence → Identify Findings → Correlate Risks → Generate Action Plan</p>
                </div>
                <Link to="/workflow" className="start-here-btn">
                    <span>Start Here</span>
                    <ArrowRight size={20} />
                </Link>
            </div>

            {/* Live API Health Status - NO mock data */}
            <HealthStatus />

            <div className="workflow-grid">
                {workflowSteps.map((step) => {
                    const Icon = step.icon;
                    return (
                        <div key={step.step} className="workflow-card">
                            <div className="workflow-card-header">
                                <div className="workflow-step-badge">
                                    Step {step.step}
                                </div>
                                <div className="workflow-status">
                                    <Clock size={14} />
                                    <span>Not run yet</span>
                                </div>
                            </div>

                            <div className="workflow-card-icon">
                                <Icon size={32} />
                            </div>

                            <h3 className="workflow-card-title">{step.title}</h3>
                            <p className="workflow-card-description">{step.description}</p>

                            <Link to={step.link} className="workflow-card-link">
                                {step.linkLabel}
                                <ArrowRight size={16} />
                            </Link>
                        </div>
                    );
                })}
            </div>

            <style>{`
                .workflow-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                    gap: 24px;
                    margin-top: 32px;
                }

                .workflow-card {
                    background: var(--glass-bg, rgba(255,255,255,0.05));
                    backdrop-filter: blur(12px);
                    border: 1px solid var(--border-color, rgba(255,255,255,0.1));
                    border-radius: 16px;
                    padding: 24px;
                    display: flex;
                    flex-direction: column;
                    transition: transform 0.2s ease, box-shadow 0.2s ease;
                }

                .workflow-card:hover {
                    transform: translateY(-4px);
                    box-shadow: 0 12px 40px rgba(0,0,0,0.3);
                }

                .workflow-card-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                }

                .workflow-step-badge {
                    background: linear-gradient(135deg, var(--primary, #6366f1), var(--primary-dark, #4f46e5));
                    color: white;
                    font-size: 12px;
                    font-weight: 600;
                    padding: 6px 12px;
                    border-radius: 20px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }

                .workflow-status {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    font-size: 12px;
                    color: var(--text-muted, #9ca3af);
                }

                .workflow-card-icon {
                    width: 64px;
                    height: 64px;
                    border-radius: 16px;
                    background: linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2));
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-bottom: 16px;
                    color: var(--primary, #6366f1);
                }

                .workflow-card-title {
                    font-size: 18px;
                    font-weight: 600;
                    margin: 0 0 8px 0;
                    color: var(--text-primary, #f9fafb);
                }

                .workflow-card-description {
                    font-size: 14px;
                    color: var(--text-muted, #9ca3af);
                    line-height: 1.6;
                    margin: 0 0 20px 0;
                    flex-grow: 1;
                }

                .workflow-card-link {
                    display: inline-flex;
                    align-items: center;
                    gap: 8px;
                    color: var(--primary, #6366f1);
                    font-size: 14px;
                    font-weight: 500;
                    text-decoration: none;
                    transition: gap 0.2s ease;
                }

                .workflow-card-link:hover {
                    gap: 12px;
                }

                .start-here-banner {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 24px;
                    padding: 32px;
                    margin-top: 32px;
                    background: linear-gradient(135deg, rgba(99,102,241,0.15), rgba(139,92,246,0.15));
                    border: 2px solid var(--primary, #6366f1);
                    border-radius: 20px;
                }

                .start-here-content h2 {
                    margin: 0 0 8px 0;
                    font-size: 24px;
                    color: var(--text-primary, #f9fafb);
                }

                .start-here-content p {
                    margin: 0;
                    color: var(--text-muted, #9ca3af);
                    font-size: 14px;
                }

                .start-here-btn {
                    display: inline-flex;
                    align-items: center;
                    gap: 12px;
                    padding: 16px 32px;
                    background: linear-gradient(135deg, var(--primary, #6366f1), #8b5cf6);
                    color: white;
                    font-size: 18px;
                    font-weight: 600;
                    text-decoration: none;
                    border-radius: 12px;
                    transition: all 0.2s ease;
                    white-space: nowrap;
                }

                .start-here-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 8px 30px rgba(99,102,241,0.4);
                }
            `}</style>
        </div>
    );
}
