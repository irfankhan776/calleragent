import React from 'react';

export function OutcomesBadge({ outcome }) {
  let classes = "";
  switch (outcome) {
    case 'Interested':
      classes = "bg-green-100 text-green-800";
      break;
    case 'Callback':
      classes = "bg-amber-100 text-amber-800";
      break;
    case 'Pitched':
      classes = "bg-blue-100 text-blue-800";
      break;
    case 'Not interested':
    default:
      classes = "bg-gray-100 text-gray-600";
      break;
  }
  
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${classes}`}>
      {outcome || 'Not interested'}
    </span>
  );
}

export default OutcomesBadge;
