import { useState } from "react";
import NavItem from "./NavItem";
import '../../CSS/SideNav.css'

import { AiFillHome } from "react-icons/ai";
import { MdReplay } from "react-icons/md";
import { FaTrophy } from "react-icons/fa";
import { RiCalendarScheduleFill, RiTeamFill } from "react-icons/ri";
import { LuPanelLeftOpen, LuPanelRightOpen } from "react-icons/lu";
import { GiFullMotorcycleHelmet } from "react-icons/gi";

const NavItems = [
  { 
    label: 'Home',
    href: '/',
    icon: <AiFillHome />,
    index: 0
  },
  { 
    label: 'Replay',
    href: '/livetiming',
    icon: <MdReplay />,
    index: 1
  },
  { 
    label: 'Standings',
    href: '/standings',
    icon: <FaTrophy />,
    index: 2,
    children: [
      { label: 'Drivers', href: '/standings/drivers', icon: <GiFullMotorcycleHelmet />, index: 0 },
      { label: 'Constructors', href: '/standings/constructors', icon: <RiTeamFill />, index: 1 }
    ],
    
  },
  { 
    label: 'Schedule',
    href: '/schedule',
    icon: <RiCalendarScheduleFill />,
    index: 3
  },
]

function SideNav() {

  const [isExpanded, setIsExpanded] = useState<boolean>(false)

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded)
  }
  const openExpanded = () => {
    setIsExpanded(true)
  }

  return <nav className={`side-bar ${isExpanded ? 'expanded' : 'collapsed'}`}>
    <button onClick={toggleExpanded}>
      {isExpanded ? <LuPanelRightOpen /> : <LuPanelLeftOpen />}
    </button>
    {NavItems.map((nav, index) => {
      return <NavItem label={nav.label} href={nav.href} icon={nav.icon} children={nav.children} openSideNav={openExpanded} isSideNavExpanded={isExpanded} index={nav.index} key={index}/>
    })}
  </nav>
}

export default SideNav