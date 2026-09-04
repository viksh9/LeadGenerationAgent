import { forwardRef, useId, type SelectHTMLAttributes } from 'react';
import { cn } from '@/utils/cn';

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, id, className, children, ...props }, ref) => {
    const generatedId = useId();
    const selectId = id ?? generatedId;
    return (
      <div>
        {label && (
          <label className="label" htmlFor={selectId}>
            {label}
          </label>
        )}
        <select ref={ref} id={selectId} className={cn('select', className)} {...props}>
          {children}
        </select>
      </div>
    );
  },
);
Select.displayName = 'Select';
