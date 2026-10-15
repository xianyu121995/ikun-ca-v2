import {requireAuthPage} from '../../lib/auth';
import HunterController from '../../components/hunter-controller';

export const dynamic='force-dynamic';
export default async function HunterPage(){
  const session=await requireAuthPage('/hunter');
  return <HunterController session={{...session,capabilities:{can_manage_hunter:session.role==='superadmin'&&!session.must_change_password}}}/>;
}
