import {createRoot} from 'react-dom/client';
import {HunterPrototype} from './Prototype';

const container=document.getElementById('hunter-ui-root');
if(!container)throw new Error('Missing isolated prototype container');
createRoot(container).render(<HunterPrototype/>);
