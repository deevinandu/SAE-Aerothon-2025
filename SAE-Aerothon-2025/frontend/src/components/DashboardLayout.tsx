import React from 'react';

interface DashboardLayoutProps {
    children: React.ReactNode;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({ children }) => {
    return (
        <div className="h-screen bg-background text-foreground p-2 md:p-3 font-sans selection:bg-primary selection:text-primary-foreground overflow-hidden flex flex-col">
            <div className="flex-1 grid grid-cols-1 md:grid-cols-12 gap-1 h-full">
                {children}
            </div>
        </div>
    );
};
