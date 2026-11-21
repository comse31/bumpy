components {
  id: "mesh"
  component: "/main/walls/destructible/destructible.mesh"
  position {
    z: -0.5
  }
}
components {
  id: "mesh_cracked"
  component: "/main/walls/destructible/cracked.mesh"
  position {
    z: -0.5
  }
}
components {
  id: "mesh_broken"
  component: "/main/walls/destructible/broken.mesh"
  position {
    z: -0.5
  }
}
components {
  id: "collision_object"
  component: "/main/walls/destructible/destructible.collisionobject"
}
components {
  id: "destructible"
  component: "/main/walls/destructible/destructible.script"
  properties {
    id: "durability"
    type: PROPERTY_TYPE_NUMBER
    value: "3"
  }
  properties {
    id: "destroyed"
    type: PROPERTY_TYPE_NUMBER
    value: "0"
  }
}
