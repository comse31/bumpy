components {
  id: "mesh"
  component: "/main/walls/block/block.mesh"
}
components {
  id: "collision_object"
  component: "/main/walls/block/block.collisionobject"
}
components {
  id: "block"
  component: "/main/walls/block/block.script"
  properties {
    id: "rows"
    type: PROPERTY_TYPE_NUMBER
    value: "8"
  }
  properties {
    id: "broken"
    type: PROPERTY_TYPE_NUMBER
    value: "0"
  }
  properties {
    id: "destroyed"
    type: PROPERTY_TYPE_NUMBER
    value: "0"
  }
}
